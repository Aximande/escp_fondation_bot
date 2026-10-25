import streamlit as st
import time
import os
import sys
import json
import pandas as pd
from datetime import datetime
import glob
import re
import traceback

# Importer les modules du projet
import config
import google_clients
import main
from reviewer_auth import require_reviewer

# Configuration de la page Streamlit
st.set_page_config(
    page_title="ESCP Workflow - Interface Reviewer",
    page_icon="📊",
    layout="wide"
)

# Constantes globales
ANALYSIS_RESULTS_DIR = main.ANALYSIS_RESULTS_DIR
PROCESSED_STATUS_FILE = main.PROCESSED_STATUS_FILE

# Styles CSS personnalisés
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        color: #003366;
        margin-bottom: 1rem;
    }
    .sub-header {
        font-size: 1.5rem;
        color: #0066cc;
        margin-bottom: 1rem;
    }
    .status-approved {
        color: green;
        font-weight: bold;
    }
    .status-needs-more-info {
        color: orange;
        font-weight: bold;
    }
    .status-incomplete {
        color: red;
        font-weight: bold;
    }
    .status-processing {
        color: blue;
        font-weight: bold;
    }
    .status-error {
        color: #dc3545; /* Rouge Bootstrap Danger */
        font-weight: bold;
    }
    .log-container {
        background-color: #f0f0f0;
        border-radius: 5px;
        padding: 10px;
        height: 300px;
        overflow-y: scroll;
        font-family: monospace;
        margin-bottom: 20px;
    }
    .history-item {
        border: 1px solid #ddd;
        border-radius: 5px;
        padding: 10px;
        margin-bottom: 10px;
        cursor: pointer;
    }
    .history-item:hover {
        background-color: #f8f9fa;
    }
</style>
""", unsafe_allow_html=True)

def initialize_session_state():
    """Initialise les variables de session si elles n'existent pas."""
    # Authentification & Données Sheet
    if 'authenticated' not in st.session_state:
        st.session_state.authenticated = False
    if 'credentials' not in st.session_state:
        st.session_state.credentials = None
    if 'sheet_data' not in st.session_state:
        st.session_state.sheet_data = None
    if 'header_row' not in st.session_state:
        st.session_state.header_row = None
    if 'data_rows' not in st.session_state:
        st.session_state.data_rows = None
    if 'df' not in st.session_state:
        st.session_state.df = None
    
    # Traitement & Affichage
    if 'processing' not in st.session_state:
        st.session_state.processing = False
    if 'current_log' not in st.session_state:
        st.session_state.current_log = []
    if 'log_updated' not in st.session_state:
        st.session_state.log_updated = False
    if 'pdf_handling_method' not in st.session_state:
        st.session_state.pdf_handling_method = 'direct'
    if 'last_analysis_id' not in st.session_state:
        st.session_state.last_analysis_id = None
    if 'processing_just_completed' not in st.session_state:
        st.session_state.processing_just_completed = False
    
    # Historique & Visualisation
    if 'viewing_history_id' not in st.session_state:
        st.session_state.viewing_history_id = None
    if 'analysis_history' not in st.session_state:
        st.session_state.analysis_history = []

def load_processed_statuses():
    """Charge les statuts depuis le fichier JSON."""
    if os.path.exists(PROCESSED_STATUS_FILE):
        try:
            with open(PROCESSED_STATUS_FILE, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError:
            st.error(f"Erreur: Le fichier de statut {PROCESSED_STATUS_FILE} n'est pas un JSON valide.")
            return {}
        except Exception as e:
            st.error(f"Erreur lors de la lecture du fichier de statut: {e}")
            return {}
    return {}

def fetch_sheet_data():
    """Récupère les données de la Google Sheet et met à jour les statuts."""
    if not st.session_state.credentials:
        st.error("Vous n'êtes pas authentifié.")
        return False
        
    try:
        sheet_data = google_clients.get_sheet_data(
            config.GOOGLE_SHEET_ID, 
            main.SHEET_RANGE, 
            st.session_state.credentials
        )
        
        if not sheet_data or len(sheet_data) < 2:
            st.warning("Aucune donnée trouvée dans la feuille ou seulement l'en-tête.")
            st.session_state.sheet_data = None
            st.session_state.df = None
            return False
            
        st.session_state.sheet_data = sheet_data
        st.session_state.header_row = sheet_data[0]
        st.session_state.data_rows = sheet_data[1:]
        
        df = pd.DataFrame(st.session_state.data_rows, columns=st.session_state.header_row)
        
        # Préparer les colonnes pour les statuts et ID d'analyse
        df['Statut Traitement'] = "Non traité"
        df['ID Analyse'] = ""
        
        processed_statuses = load_processed_statuses()
        for i, row in df.iterrows():
            timestamp = row.get('Timestamp', '')
            email = row.get('email of the responsible person', '')
            row_key = f"{timestamp}_{email}"
            
            if row_key in processed_statuses:
                df.at[i, 'Statut Traitement'] = processed_statuses[row_key].get('status', 'Traité')
                df.at[i, 'ID Analyse'] = processed_statuses[row_key].get('analysis_id', '')
        
        st.session_state.df = df
        return True
    except Exception as e:
        st.error(f"Erreur lors de la récupération/traitement des données Sheet: {str(e)}")
        return False

def get_analysis_history():
    """Récupère la liste des répertoires d'analyse triés par date (plus récent d'abord)."""
    history = []
    if os.path.exists(ANALYSIS_RESULTS_DIR):
        try:
            # Utiliser glob pour lister les sous-répertoires
            subdirs = [d for d in glob.glob(os.path.join(ANALYSIS_RESULTS_DIR, '*')) if os.path.isdir(d)]
            # Extraire les timestamps des noms de répertoires pour le tri
            dated_dirs = []
            for d in subdirs:
                basename = os.path.basename(d)
                # Essayer d'extraire la date YYYYMMDD_HHMMSS du début
                match = re.match(r'(\d{8}_\d{6})', basename)
                if match:
                    try:
                        # Convertir en objet datetime pour un tri fiable
                        dt = datetime.strptime(match.group(1), '%Y%m%d_%H%M%S')
                        dated_dirs.append((dt, basename))
                    except ValueError:
                        dated_dirs.append((datetime.min, basename)) # Mettre au début en cas d'erreur
                else:
                    dated_dirs.append((datetime.min, basename)) # Mettre au début si pas de date trouvée
            
            # Trier par date, du plus récent au plus ancien
            dated_dirs.sort(key=lambda item: item[0], reverse=True)
            history = [name for dt, name in dated_dirs]
        except Exception as e:
            st.error(f"Erreur lors de la lecture de l'historique des analyses: {e}")
    return history

def display_analysis_results(analysis_id: str):
    """Affiche les résultats d'une analyse spécifique."""
    analysis_dir = os.path.join(ANALYSIS_RESULTS_DIR, analysis_id)
    if not os.path.isdir(analysis_dir):
        st.error(f"Le répertoire d'analyse '{analysis_id}' n'existe pas.")
        return

    st.markdown(f"<h3 class='sub-header'>Résultats de l'analyse : {analysis_id}</h3>", unsafe_allow_html=True)

    # Chemins des fichiers attendus
    applicant_email_path = os.path.join(analysis_dir, "applicant_email.html")
    internal_email_path = os.path.join(analysis_dir, "internal_email.html")
    log_path = os.path.join(analysis_dir, "log.md")
    assessment_path = os.path.join(analysis_dir, "overall_assessment.json")

    # Lire le statut depuis le fichier d'évaluation
    status = "Inconnu"
    if os.path.exists(assessment_path):
        try:
            with open(assessment_path, 'r', encoding="utf-8") as f:
                assessment_data = json.load(f)
            status = assessment_data.get('status', 'Inconnu').upper()
            # Appliquer un style basé sur le statut
            status_class = ""
            if status == 'APPROVED': status_class = "status-approved"
            elif status == 'NEEDS_MORE_INFO': status_class = "status-needs-more-info"
            elif status == 'INCOMPLETE': status_class = "status-incomplete"
            elif 'ERROR' in status: status_class = "status-error"
            st.markdown(f'Statut: <span class="{status_class}">{status}</span>', unsafe_allow_html=True)
            st.json(assessment_data) # Afficher le JSON de l'évaluation
        except Exception as e:
            st.warning(f"Impossible de lire ou parser le fichier d'évaluation ({assessment_path}): {e}")
    else:
        st.warning(f"Fichier d'évaluation ({assessment_path}) non trouvé.")

    tab1, tab2, tab3 = st.tabs(["Email Demandeur", "Email Interne", "Log Détaillé"])

    with tab1:
        if os.path.exists(applicant_email_path):
            try:
                with open(applicant_email_path, "r", encoding="utf-8") as f:
                    html_content = f.read()
                if html_content.strip():
                    st.components.v1.html(html_content, height=600, scrolling=True)
                else:
                    st.info("Le fichier email demandeur existe mais est vide.")
            except Exception as e:
                st.error(f"Erreur lecture/affichage email demandeur: {str(e)}")
        else:
            st.info("Aucun fichier email demandeur trouvé pour cette analyse.")

    with tab2:
        if os.path.exists(internal_email_path):
            try:
                with open(internal_email_path, "r", encoding="utf-8") as f:
                    html_content = f.read()
                if html_content.strip():
                    st.components.v1.html(html_content, height=600, scrolling=True)
                else:
                    st.info("Le fichier email interne existe mais est vide.")
            except Exception as e:
                st.error(f"Erreur lecture/affichage email interne: {str(e)}")
        else:
            st.info("Aucun fichier email interne trouvé pour cette analyse.")

    with tab3:
        if os.path.exists(log_path):
            try:
                with open(log_path, "r", encoding="utf-8") as f:
                    log_content = f.read()
                # Effectuer le remplacement avant la f-string
                log_html_content = log_content.replace('\n', '<br>')
                # Afficher le log brut dans un conteneur scrollable
                st.markdown(f"<div class='log-container'>{log_html_content}</div>", unsafe_allow_html=True)
            except Exception as e:
                st.error(f"Erreur lecture/affichage log: {str(e)}")
        else:
            st.info("Aucun fichier log trouvé pour cette analyse.")

def main_interface():
    """Affiche l'interface principale après authentification."""
    st.markdown("<h1 class='main-header'>ESCP Workflow - Interface Reviewer</h1>", unsafe_allow_html=True)
    
    # --- Sidebar --- 
    with st.sidebar:
        st.markdown("<h2 class='sub-header'>Actions</h2>", unsafe_allow_html=True)
        if st.button("Rafraîchir les données Sheet", type="primary"):
            with st.spinner("Récupération des données..."):
                fetch_sheet_data()
            st.success("Données Sheet mises à jour!")
        
        st.divider()
        st.markdown("<h2 class='sub-header'>Options d'analyse</h2>", unsafe_allow_html=True)
        pdf_method = st.radio(
            "Méthode d'analyse des PDF",
            options=["PDF direct", "Convertir en image"],
            index=0 if st.session_state.pdf_handling_method == 'direct' else 1,
            key='pdf_method_selector'
        )
        st.session_state.pdf_handling_method = 'direct' if pdf_method == "PDF direct" else 'image'
        
        st.divider()
        # Section Historique dans la sidebar
        st.markdown("<h2 class='sub-header'>Historique des Analyses</h2>", unsafe_allow_html=True)
        st.session_state.analysis_history = get_analysis_history()
        if st.session_state.analysis_history:
            selected_history_id = st.selectbox(
                "Voir une analyse précédente", 
                options=["---"] + st.session_state.analysis_history,
                index=0,
                key='history_selector'
            )
            if selected_history_id != "---":
                st.session_state.viewing_history_id = selected_history_id
                st.session_state.last_analysis_id = None
                st.session_state.processing_just_completed = False
            else:
                # Si on sélectionne "---", arrêter de voir l'historique
                if st.session_state.viewing_history_id:
                    st.session_state.viewing_history_id = None
        else:
            st.info("Aucune analyse précédente trouvée.")
        
        st.divider()
        if st.button("Se déconnecter"):
            # Réinitialiser l'état de session
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()
    
    # --- Chargement initial des données --- 
    if st.session_state.df is None:
        with st.spinner("Chargement initial des données Sheet..."):
            fetch_sheet_data()
    
    # --- Contenu Principal --- 
    
    # Afficher les détails de l'historique si sélectionné
    if st.session_state.viewing_history_id:
        display_analysis_results(st.session_state.viewing_history_id)
        st.markdown("---")
        if st.button("Retour à la liste principale"):
            st.session_state.viewing_history_id = None
            st.rerun()
        return
    
    # Afficher les résultats du dernier traitement si applicable
    if st.session_state.processing_just_completed:
        st.success("Traitement terminé avec succès ! Les résultats sont disponibles ci-dessous.")
        st.session_state.processing_just_completed = False
        # Afficher directement les résultats sans bouton "Afficher"
        if st.session_state.last_analysis_id:
            display_analysis_results(st.session_state.last_analysis_id)
            st.markdown("---")
        else:
            st.warning("ID de la dernière analyse non trouvé. Impossible d'afficher les résultats.")
    
    # Afficher le tableau des réponses Sheet seulement si des données existent
    if st.session_state.df is not None:
        st.markdown("<h2 class='sub-header'>Réponses du formulaire</h2>", unsafe_allow_html=True)
        col1, col2 = st.columns(2)
        with col1:
            filter_status = st.selectbox(
                "Filtrer par statut",
                ["Tous", "Non traité", "Traité", "APPROVED", "NEEDS_MORE_INFO", "INCOMPLETE", "ERROR"],
                key='status_filter'
            )
        with col2:
            search_query = st.text_input("Rechercher par nom/email", key='search_input')
        
        filtered_df = st.session_state.df.copy()
        if filter_status != "Tous":
            # Gérer le cas "Traité" qui peut englober plusieurs statuts finaux
            if filter_status == "Traité":
                statuses_to_filter = ["APPROVED", "NEEDS_MORE_INFO", "INCOMPLETE", "ERROR"]
                filtered_df = filtered_df[filtered_df['Statut Traitement'].isin(statuses_to_filter)]
            else:
                filtered_df = filtered_df[filtered_df['Statut Traitement'].astype(str).str.contains(filter_status, case=False, na=False)]
        if search_query:
            name_email_columns = [col for col in filtered_df.columns if 'name' in col.lower() or 'email' in col.lower() or 'project' in col.lower()]
            mask = pd.Series(False, index=filtered_df.index)
            for col in name_email_columns:
                mask = mask | filtered_df[col].astype(str).str.contains(search_query, case=False, na=False)
            filtered_df = filtered_df[mask]
        
        st.dataframe(filtered_df, use_container_width=True)
        
        st.markdown("<h2 class='sub-header'>Traiter une réponse</h2>", unsafe_allow_html=True)
        col1, col2 = st.columns([3, 1])
        with col1:
            # Filtrer les options pour n'afficher que les réponses pertinentes
            available_options = filtered_df.index.tolist()
            selected_index_in_filtered = st.selectbox(
                "Sélectionner une réponse dans la liste filtrée",
                options=available_options,
                format_func=lambda i: f"{filtered_df.loc[i].get('Timestamp', 'N/A')} - {filtered_df.loc[i].get('Responsible person', 'N/A')} - {filtered_df.loc[i].get('Project Name', 'N/A')} (Statut: {filtered_df.loc[i].get('Statut Traitement', '?')})",
                key='response_selector'
            )
        with col2:
            if st.button("Lancer le traitement", type="primary", disabled=st.session_state.processing or selected_index_in_filtered is None):
                if selected_index_in_filtered is not None:
                    st.session_state.processing = True
                    st.session_state.current_log = []
                    st.session_state.log_updated = False
                    # Stocker l'index global correspondant à l'index filtré
                    st.session_state.selected_global_index = selected_index_in_filtered
                    st.session_state.viewing_history_id = None
                    st.rerun()
                else:
                    st.warning("Veuillez sélectionner une réponse à traiter.")
    else:
        st.info("Aucune donnée à afficher. Cliquez sur 'Rafraîchir les données Sheet' ou vérifiez la connexion.")

def processing_interface():
    """Affiche l'interface de traitement pendant qu'une réponse est en cours de traitement."""
    st.markdown("<h1 class='main-header'>ESCP Workflow - Traitement en cours</h1>", unsafe_allow_html=True)
    
    # Afficher les détails de la réponse en cours de traitement (utiliser l'index global stocké)
    selected_row = st.session_state.df.loc[st.session_state.selected_global_index]
    
    st.markdown(f"""
    <div style='background-color: #f0f8ff; padding: 15px; border-radius: 5px; margin-bottom: 20px;'>
        <h3>Traitement de la réponse:</h3>
        <p><strong>Projet:</strong> {selected_row.get('Project Name', 'N/A')}</p>
        <p><strong>Responsable:</strong> {selected_row.get('Responsible person', 'N/A')}</p>
        <p><strong>Email:</strong> {selected_row.get('email of the responsible person', 'N/A')}</p>
        <p><strong>Date:</strong> {selected_row.get('Timestamp', 'N/A')}</p>
        <p><strong>Méthode d'analyse PDF:</strong> {"PDF direct" if st.session_state.pdf_handling_method == 'direct' else "Conversion en image"}</p>
    </div>
    """, unsafe_allow_html=True)
    
    log_container = st.empty()
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    def update_log_and_progress(text, progress):
        if text.strip():
            log_entry = f"[{datetime.now().strftime('%H:%M:%S')}] {text.strip()}"
            st.session_state.current_log.append(log_entry)
            log_html = "<div class='log-container'>"
            for entry in st.session_state.current_log:
                log_html += f"<p>{entry}</p>"
            log_html += "</div>"
            log_container.markdown(log_html, unsafe_allow_html=True)
        if progress is not None:
            progress_bar.progress(progress)
            status_text.text(f"Progression: {progress}%")
    
    if not st.session_state.log_updated:
        st.session_state.log_updated = True
        update_log_and_progress("Démarrage du traitement...", 5)
        
        original_stdout = sys.stdout
        original_stderr = sys.stderr
        
        class LogCapture:
            def __init__(self, is_stderr=False):
                self.is_stderr = is_stderr
                self.original_stream = original_stderr if is_stderr else original_stdout
            def write(self, text):
                update_log_and_progress(text, None)
                self.original_stream.write(text)
            def flush(self):
                self.original_stream.flush()
        
        sys.stdout = LogCapture()
        sys.stderr = LogCapture(is_stderr=True)
        
        try:
            header_row = st.session_state.header_row
            data_row = st.session_state.data_rows[st.session_state.selected_global_index]
            credentials = st.session_state.credentials
            pdf_method = st.session_state.pdf_handling_method
            
            update_log_and_progress("Lancement de process_form_response...", 10)
            
            analysis_id = main.process_form_response(header_row, data_row, credentials, pdf_method)
            
            update_log_and_progress("Traitement principal terminé.", 90)
            
            sys.stdout = original_stdout
            sys.stderr = original_stderr
            
            if analysis_id:
                st.session_state.last_analysis_id = analysis_id
                update_log_and_progress(f"Analyse terminée avec succès. ID: {analysis_id}", 100)
                fetch_sheet_data()
                st.session_state.processing_just_completed = True
            else:
                update_log_and_progress("Erreur critique durant le traitement, ID d'analyse non retourné.", 100)
                st.session_state.processing_just_completed = False
            
            status_text.text("Traitement terminé !")
            if st.button("Revenir à l'interface principale", type="primary"):
                st.session_state.processing = False
                st.rerun()
            
        except Exception as e:
            sys.stdout = original_stdout
            sys.stderr = original_stderr
            st.session_state.current_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] ERREUR GLOBALE: {str(e)}")
            st.session_state.current_log.append(traceback.format_exc())
            update_log_and_progress(f"Erreur Globale: {e}", 100)
            status_text.error("Une erreur est survenue durant le traitement.")
            st.session_state.processing = False
            st.session_state.processing_just_completed = False
            if st.button("Revenir à l'interface principale", type="primary"):
                st.rerun()
    else:
        update_log_and_progress("Mise à jour de l'affichage des logs...", None)
        if st.session_state.processing:
            status_text.text("Traitement en cours...")
        else:
            if st.button("Revenir à l'interface principale", type="primary"):
                st.rerun()

# Application principale
def main_app():
    """Point d'entrée de l'application Streamlit."""
    # Verify the OIDC identity on every rerun, before data or processing is shown.
    if not require_reviewer(st, google_clients.get_google_credentials):
        return
    initialize_session_state()
    
    if st.session_state.processing:
        processing_interface()
    else:
        main_interface()

if __name__ == "__main__":
    main_app()
