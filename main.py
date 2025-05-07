import os
import shutil # Pour la suppression du dossier de téléchargement
import json
import time
import traceback # Ajouter traceback pour le logger
import re # Pour nettoyer les noms de fichiers

# Importer les modules du projet
import config
import google_clients
import analysis
import openai_client
import email_handler

# --- Configuration Globale --- 
ANALYSIS_RESULTS_DIR = "analysis_results"
DOWNLOAD_FOLDER_BASE = "downloads"
PROCESSED_STATUS_FILE = "processed_responses.json"

# --- Log Helper (Modifié) ---
def append_log(log_file_path: str, section_title: str, content: str, is_json: bool = False, is_html: bool = False):
    """Ajoute une section à un fichier log Markdown spécifique."""
    try:
        # Assurer que le répertoire du log existe
        log_dir = os.path.dirname(log_file_path)
        os.makedirs(log_dir, exist_ok=True)
        
        with open(log_file_path, "a", encoding="utf-8") as log_f:
            log_f.write(f"## {section_title} ({time.strftime('%Y-%m-%d %H:%M:%S')})\n\n")
            if is_json:
                try:
                    if isinstance(content, (dict, list)):
                        formatted_content = json.dumps(content, indent=2, ensure_ascii=False)
                    else: 
                        parsed_json = json.loads(content)
                        formatted_content = json.dumps(parsed_json, indent=2, ensure_ascii=False)
                    log_f.write(f"```json\n{formatted_content}\n```\n\n")
                except (json.JSONDecodeError, TypeError):
                    log_f.write(f"```\n{str(content)}\n```\n\n") # Fallback
            elif is_html:
                log_f.write(f"{content}\n\n")
            else:
                log_f.write(f"```\n{content}\n```\n\n")
            log_f.write("---\n\n")
    except Exception as e:
        print(f"WARN: Impossible d'écrire dans le fichier log {log_file_path}: {e}")
        traceback.print_exc()

# --- Constantes & Configuration (Sheet) --- 
# !! Adapter ces noms aux titres EXACTS de vos colonnes dans la Google Sheet !!
COLUMN_MAPPING = {
    'Timestamp': 'timestamp',
    'Project Name': 'project_name',
    'Campus': 'campus',
    'Responsible person': 'responsible_name',
    'email of the responsible person': 'responsible_email',
    'EOTP (for campuses outside Paris, please enter the Campus EOTP, all payments will be made to Paris Campus). One EOTP only  per form': 'eotp_code',
    'Axis': 'axis',
    'Total Amount Allocated in the forecast 2025 Budget': 'total_allocated',
    'Amount Spent in 2025 (note: in case of overbudget, only the forecast budget will be paid as a maximum)': 'amount_spent',
    'Amount Already paid in 2025 by the ESCP foundation (if relevent, if not relevant put 0)': 'amount_already_paid',
    'Remaining amount to pay by ESCP Foundation': 'remaining_amount',
    'Download the realised budget of the project': 'budget_file_urls',
    'Briefly describe your project': 'project_description',
    'Main objectives persued': 'project_objectives',
    'evaluate your project (goals reached and implementation)': 'project_evaluation',
    'Key milestones achieved during this reporting period': 'project_milestones',
    'number of beneficiaries directly impacted': 'kpi_beneficiaries',
    'Key feedback or testimonials from beneficiaries': 'kpi_feedback',
    'Notable positive outcomes observed (impact on rankings, students, for ESCP...)': 'kpi_outcomes',
    'Number of communication pieces published (articles, social media posts)': 'kpi_comms',
    'Please upload your files here': 'supporting_files_urls',
    'Signature': 'signature_confirmation'
}
SHEET_RANGE = "responses!A:Z" # <<< ADAPTEZ LE NOM DE L'ONGLET ET LA PLAGE SI NÉCESSAIRE

def sanitize_filename(name):
    """Nettoie une chaîne pour l'utiliser comme nom de fichier/répertoire."""
    # Garder les caractères alphanumériques, underscores, et tirets
    sanitized = re.sub(r'[^\w-]', '_', str(name))
    # Remplacer les espaces multiples par un seul underscore
    sanitized = re.sub(r'_\+', '_', sanitized)
    # Supprimer les underscores au début et à la fin
    sanitized = sanitized.strip('_')
    return sanitized[:100] # Limiter la longueur

def parse_sheet_row(header_row: list, data_row: list) -> dict:
    """Convertit une ligne de la feuille en dictionnaire structuré."""
    parsed_data = {}
    header_map = {header: idx for idx, header in enumerate(header_row)}
    
    for col_name, data_key in COLUMN_MAPPING.items():
        if col_name in header_map:
            col_index = header_map[col_name]
            if col_index < len(data_row):
                parsed_data[data_key] = data_row[col_index]
            else:
                parsed_data[data_key] = None
        else:
            print(f"WARN: Colonne attendue '{col_name}' non trouvée dans l'en-tête.")
            parsed_data[data_key] = None
            
    numeric_fields = ['total_allocated', 'amount_spent', 'amount_already_paid', 'remaining_amount']
    for key in numeric_fields:
        if parsed_data.get(key):
            try:
                value_str = str(parsed_data[key]).replace('€', '').replace(',', '.').strip()
                parsed_data[key] = float(value_str)
            except ValueError:
                print(f"WARN: Impossible de convertir '{parsed_data[key]}' en nombre pour '{key}'.")

    return parsed_data

def save_json_result(output_dir: str, filename: str, data: dict):
    """Sauvegarde un dictionnaire en fichier JSON dans le répertoire spécifié."""
    filepath = os.path.join(output_dir, filename)
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"Résultat JSON sauvegardé dans: {filepath}")
    except Exception as e:
        print(f"WARN: Impossible de sauvegarder le JSON {filepath}: {e}")

def process_form_response(header_row: list, data_row: list, credentials, pdf_handling_method: str = 'direct'):
    """Traite une seule réponse de formulaire et stocke les résultats dans un répertoire dédié."""
    print("\n======================================================================")
    response_timestamp = time.strftime('%Y%m%d_%H%M%S')
    
    # 1. Parser les données et déterminer l'identifiant
    form_data = parse_sheet_row(header_row, data_row)
    responsible_email = form_data.get('responsible_email', 'no_email')
    project_name = form_data.get('project_name', 'no_project_name')
    
    if not responsible_email or responsible_email == 'no_email':
        print("ERREUR CRITIQUE: Email du responsable manquant. Ligne ignorée.")
        return None # Indiquer qu'aucun répertoire n'a été créé
    
    # Créer un identifiant unique et un nom de répertoire pour ce traitement
    response_id = f"{response_timestamp}_{sanitize_filename(project_name)}_{sanitize_filename(responsible_email)}"
    current_analysis_dir = os.path.join(ANALYSIS_RESULTS_DIR, response_id)
    os.makedirs(current_analysis_dir, exist_ok=True)
    
    # Définir le chemin du fichier log spécifique pour ce traitement
    log_file_path = os.path.join(current_analysis_dir, "log.md")
    
    print(f"Traitement Réponse ID: {response_id}")
    print(f"Répertoire de sortie: {current_analysis_dir}")
    print("======================================================================")
    
    append_log(log_file_path, "Début Traitement", f"ID: {response_id}\nEmail: {responsible_email}\nProjet: {project_name}")

    # Sauvegarder les données du formulaire initial
    save_json_result(current_analysis_dir, "form_data.json", form_data)
    append_log(log_file_path, "Étape 1: Données Formulaire", form_data, is_json=True)

    # 2. Créer le dossier de téléchargement spécifique
    current_download_folder = os.path.join(current_analysis_dir, DOWNLOAD_FOLDER_BASE)
    os.makedirs(current_download_folder, exist_ok=True)

    # 3. Télécharger les fichiers
    print("\n--- Téléchargement des fichiers --- ")
    budget_file_path = None
    supporting_file_paths = []
    downloaded_files_log = []
    all_files_urls = []
    if form_data.get('budget_file_urls'):
         all_files_urls.extend([url.strip() for url in form_data['budget_file_urls'].split(',') if url.strip()])
    if form_data.get('supporting_files_urls'):
         all_files_urls.extend([url.strip() for url in form_data['supporting_files_urls'].split(',') if url.strip()])
         
    for url in all_files_urls:
        file_id = google_clients.extract_drive_file_id(url)
        if file_id:
            # Télécharger dans le dossier de téléchargement spécifique
            downloaded_path = google_clients.download_drive_file(file_id, credentials, current_download_folder)
            if downloaded_path:
                file_type = "support" # Default type

                # Safely check if the current URL is part of the budget file URLs
                budget_file_urls_str = form_data.get('budget_file_urls')
                is_from_budget_list = False
                if isinstance(budget_file_urls_str, str) and budget_file_urls_str.strip():
                    if url in [u.strip() for u in budget_file_urls_str.split(',') if u.strip()]:
                        is_from_budget_list = True
                
                if is_from_budget_list:
                    if not budget_file_path: # First file from budget list becomes the main budget file
                        budget_file_path = downloaded_path
                        file_type = "budget"
                    else: # Subsequent files from budget list (or if main is already taken) are supporting
                        supporting_file_paths.append(downloaded_path)
                else: # File is not from budget list, so it's a supporting file
                    supporting_file_paths.append(downloaded_path)
                
                downloaded_files_log.append({"url": url, "path": downloaded_path, "type": file_type})
                print(f"-> Téléchargé ({file_type}): {downloaded_path}")
            else:
                downloaded_files_log.append({"url": url, "id": file_id, "status": "Échec téléchargement"})
                print(f"-> Échec téléchargement ID: {file_id}")
        else:
            downloaded_files_log.append({"url": url, "status": "ID non extrait"})
            print(f"-> ID non extrait: {url}")
    append_log(log_file_path, "Étape 3: Téléchargements", json.dumps(downloaded_files_log, indent=2), is_json=True)

    # 4. Analyse du Budget Excel
    budget_analysis_result = None
    log_title_budget = "Étape 4: Analyse Budget (Python)"
    if budget_file_path:
        form_data_for_excel_analysis = {
            k: form_data.get(k) for k in 
            ['total_allocated', 'amount_spent', 'amount_already_paid', 'remaining_amount']
        }
        budget_analysis_result = analysis.analyse_budget_excel(budget_file_path, form_data_for_excel_analysis)
        print("\n--- Résultat Analyse Budget Excel (Python) ---")
        budget_analysis_json_str = json.dumps(budget_analysis_result, indent=2, ensure_ascii=False)
        print(budget_analysis_json_str)
        save_json_result(current_analysis_dir, "budget_analysis.json", budget_analysis_result)
        append_log(log_file_path, log_title_budget, budget_analysis_result, is_json=True)
    else:
        print("\nWARN: Aucun fichier budget identifié. Analyse Excel ignorée.")
        budget_analysis_result = {"completeness": "incomplete", "issues_identified": ["Fichier budget non trouvé/identifié."]}
        save_json_result(current_analysis_dir, "budget_analysis.json", budget_analysis_result)
        append_log(log_file_path, log_title_budget, "Fichier budget non trouvé/identifié.")

    # 5. Analyse des Pièces Justificatives
    supporting_docs_analysis_results = []
    log_title_pj_summary = "Étape 5: Analyse PJ (OpenAI)"
    if supporting_file_paths:
        print("\n--- Analyse des Pièces Justificatives (OpenAI) --- ")
        project_context = {
            'project_name': form_data.get('project_name'),
            'project_description': form_data.get('project_description'),
            'expense_categories': ""
        }
        append_log(log_file_path, log_title_pj_summary, f"Début analyse de {len(supporting_file_paths)} PJ(s)... Méthode PDF: {pdf_handling_method}")
        for i, doc_path in enumerate(supporting_file_paths):
            doc_basename = os.path.basename(doc_path)
            print(f"Analyse PJ {i+1}/{len(supporting_file_paths)}: {doc_basename}")
            # Passer la méthode PDF choisie
            doc_analysis = openai_client.analyse_supporting_document(
                doc_path, 
                project_context,
                pdf_handling_method=pdf_handling_method 
            )
            if doc_analysis:
                 doc_analysis['_source_file_'] = doc_basename # Ajouter le nom du fichier source
                 supporting_docs_analysis_results.append(doc_analysis)
            else:
                 print(f"-> Échec analyse OpenAI pour: {doc_path}")
                 supporting_docs_analysis_results.append({
                     "_source_file_": doc_basename,
                     "document_type": "Erreur Analyse", 
                     "conclusion": "L'analyse OpenAI a échoué."
                 })
            time.sleep(1)
        # Sauvegarder le résultat combiné des analyses PJ
        save_json_result(current_analysis_dir, "supporting_docs_analysis.json", supporting_docs_analysis_results)
        append_log(log_file_path, f"{log_title_pj_summary} - Résultats", supporting_docs_analysis_results, is_json=True)
    else:
        print("\nINFO: Aucune pièce justificative à analyser.")
        save_json_result(current_analysis_dir, "supporting_docs_analysis.json", []) # Sauver une liste vide
        append_log(log_file_path, log_title_pj_summary, "Aucune pièce justificative trouvée.")

    # 6. Évaluation Globale du Dossier
    print("\n--- Évaluation Globale du Dossier (OpenAI) --- ")
    log_title_global = "Étape 6: Évaluation Globale"
    append_log(log_file_path, f"{log_title_global} - Input", f"Lancement avec données formulaire, analyse budget, et {len(supporting_docs_analysis_results)} analyses PJ.")
    
    overall_assessment_result = openai_client.assess_overall_dossier(
        form_data,
        budget_analysis_result,
        supporting_docs_analysis_results
    )
    
    if overall_assessment_result:
        print("\n--- Résultat Évaluation Globale ---")
        overall_json_str = json.dumps(overall_assessment_result, indent=2, ensure_ascii=False)
        print(overall_json_str)
        save_json_result(current_analysis_dir, "overall_assessment.json", overall_assessment_result)
        append_log(log_file_path, f"{log_title_global} - Output", overall_assessment_result, is_json=True)
    else:
        print("ERREUR CRITIQUE: Échec de l'évaluation globale.")
        append_log(log_file_path, f"{log_title_global} - Output", "Échec de l'appel OpenAI.")
        # Enregistrer un statut d'erreur
        update_processed_status(response_id, form_data, "ERROR_ASSESSMENT")
        return response_id # Retourner l'ID même en cas d'échec partiel

    # 7. Préparation et Création des Brouillons d'Email
    print("\n--- Préparation et Création des Brouillons Email --- ")
    recipient_email = form_data.get('responsible_email')
    internal_email_address = config.INTERNAL_REVIEW_EMAIL
    final_status = overall_assessment_result.get('status', 'INCOMPLETE').upper()
    
    applicant_data = {
        'responsible_name': form_data.get('responsible_name', '[Nom Manquant]'),
        'project_name': form_data.get('project_name', '[Projet Manquant]'),
        'responsible_email': recipient_email,
        'remaining_amount': form_data.get('remaining_amount', '[Montant Manquant]')
    }
    
    # --- Email Demandeur --- 
    log_title_email_applicant = "Étape 7a: Génération Email Demandeur"
    append_log(log_file_path, f"{log_title_email_applicant} - Input", f"Statut: {final_status}")
    body_html_applicant = openai_client.generate_applicant_html_email(
        assessment_data=overall_assessment_result,
        applicant_data=applicant_data,
        budget_analysis_data=budget_analysis_result,
        supporting_docs_data=supporting_docs_analysis_results
    )
    
    subject_applicant = f"[Action Requise] Mise à jour rapport - {applicant_data['project_name']}"
    if final_status == 'APPROVED': subject_applicant = f"[Approuvé] Rapport {applicant_data['project_name']}"
    elif final_status == 'NEEDS_MORE_INFO': subject_applicant = f"[Infos Requises] Rapport {applicant_data['project_name']}"
    elif final_status == 'INCOMPLETE': subject_applicant = f"[Incomplet] Rapport {applicant_data['project_name']}"
    elif final_status == 'ERROR_PARSING_RESPONSE': subject_applicant = f"[Erreur Évaluation] Rapport {applicant_data['project_name']}"

    applicant_email_path = os.path.join(current_analysis_dir, "applicant_email.html")
    if body_html_applicant:
        try:
            with open(applicant_email_path, "w", encoding="utf-8") as f_html:
                f_html.write(body_html_applicant)
            print(f"Email HTML Demandeur sauvegardé dans: {applicant_email_path}")
            append_log(log_file_path, f"{log_title_email_applicant} - Output", f"Email sauvegardé dans {applicant_email_path}")
            print(f"Préparation brouillon pour DEMANDEUR: {recipient_email}")
            google_clients.create_gmail_draft(credentials, recipient_email, subject_applicant, body_html_applicant)
        except Exception as e:
            print(f"WARN: Erreur sauvegarde/brouillon Email Demandeur: {e}")
            append_log(log_file_path, f"{log_title_email_applicant} - ERREUR", f"Erreur sauvegarde/brouillon: {e}")
    else:
        append_log(log_file_path, f"{log_title_email_applicant} - Output", "Échec génération HTML.")
        print("ERREUR: Échec génération email demandeur.")
        
    # --- Email Interne --- 
    if internal_email_address:
        log_title_email_internal = "Étape 7b: Génération Email Interne"
        append_log(log_file_path, f"{log_title_email_internal} - Input", f"Statut: {final_status}")
        body_html_internal = openai_client.generate_internal_review_email(
            assessment_data=overall_assessment_result,
            applicant_data=applicant_data,
            budget_analysis_data=budget_analysis_result,
            supporting_docs_data=supporting_docs_analysis_results,
            validator_name="Équipe de la Fondation ESCP" 
        )
        
        subject_internal = f"[Revue Dossier] {applicant_data['project_name']} - Statut: {final_status}"
        internal_email_path = os.path.join(current_analysis_dir, "internal_email.html")
        
        if body_html_internal:
            try:
                with open(internal_email_path, "w", encoding="utf-8") as f_html_int:
                    f_html_int.write(body_html_internal)
                print(f"Email HTML Interne sauvegardé dans: {internal_email_path}")
                append_log(log_file_path, f"{log_title_email_internal} - Output", f"Email sauvegardé dans {internal_email_path}")
                print(f"Préparation brouillon pour INTERNE: {internal_email_address}")
                # Joindre le log spécifique au brouillon interne
                google_clients.create_gmail_draft(
                    credentials, 
                    internal_email_address, 
                    subject_internal, 
                    body_html_internal, 
                    attachment_paths=[log_file_path] # Joindre le log spécifique
                )
            except Exception as e:
                 print(f"WARN: Erreur sauvegarde/brouillon Email Interne: {e}")
                 append_log(log_file_path, f"{log_title_email_internal} - ERREUR", f"Erreur sauvegarde/brouillon: {e}")
        else:
            append_log(log_file_path, f"{log_title_email_internal} - Output", "Échec génération HTML interne.")
            print("ERREUR: Échec génération email interne.")
    else:
        print("INFO: Email interne non configuré, brouillon interne non créé.")
        append_log(log_file_path, "Étape 7b: Génération Email Interne", "Skipped: INTERNAL_REVIEW_EMAIL non défini.")
        
    # 8. Mettre à jour le statut global du traitement
    update_processed_status(response_id, form_data, final_status)
    
    print("\n======================================================================")
    print(f"Traitement terminé pour ID: {response_id}")
    print("======================================================================")
    return response_id # Retourner l'ID du répertoire créé

def update_processed_status(response_id: str, form_data: dict, status: str):
    """Met à jour le fichier JSON de suivi des réponses traitées."""
    try:
        processed_data = {}
        if os.path.exists(PROCESSED_STATUS_FILE):
            with open(PROCESSED_STATUS_FILE, 'r') as f:
                processed_data = json.load(f)
                
        # Utiliser une clé plus simple si possible (timestamp + email)
        row_key = f"{form_data.get('timestamp', '')}_{form_data.get('responsible_email', '')}"
        
        processed_data[row_key] = {
            "analysis_id": response_id, # Lier au répertoire d'analyse
            "timestamp": form_data.get('timestamp', ''),
            "email": form_data.get('responsible_email', ''),
            "project": form_data.get('project_name', 'N/A'),
            "processed_date": time.strftime('%Y-%m-%d %H:%M:%S'),
            "status": status
        }
        
        with open(PROCESSED_STATUS_FILE, 'w') as f:
            json.dump(processed_data, f, indent=2)
            
    except Exception as e:
        print(f"WARN: Impossible de mettre à jour le fichier de statut {PROCESSED_STATUS_FILE}: {e}")

def main(run_all=False, pdf_handling_method='direct'):
    """Fonction principale orchestrant le workflow.
    Args:
        run_all: Si True, traite toutes les lignes non marquées comme traitées.
                 Si False (défaut), traite uniquement la première ligne de données.
        pdf_handling_method: Méthode d'analyse PDF ('direct' ou 'image').
    """
    print("Lancement du workflow d'évaluation ESCP...")
    credentials = None
    try:
        # 1. Authentification Google
        credentials = google_clients.get_google_credentials()
        if not credentials:
            print("ERREUR: Impossible d'obtenir les identifiants Google. Arrêt.")
            return
            
        # 2. Récupération des données Sheets
        if not config.GOOGLE_SHEET_ID:
            print("ERREUR: GOOGLE_SHEET_ID non défini dans .env. Arrêt.")
            return
            
        sheet_data = google_clients.get_sheet_data(config.GOOGLE_SHEET_ID, SHEET_RANGE, credentials)
        
        if not sheet_data or len(sheet_data) < 2:
            print("INFO: Aucune donnée trouvée dans la feuille ou seulement l'en-tête. Arrêt.")
            return
            
        header_row = sheet_data[0]
        data_rows = sheet_data[1:] 
        
        # Charger les statuts des réponses déjà traitées
        processed_statuses = {}
        if os.path.exists(PROCESSED_STATUS_FILE):
            with open(PROCESSED_STATUS_FILE, 'r') as f:
                processed_statuses = json.load(f)
        
        if run_all:
            print("Mode: Traitement de toutes les nouvelles lignes.")
            processed_count = 0
            for i, row in enumerate(data_rows):
                # Créer une clé pour vérifier si la ligne a déjà été traitée
                form_data_temp = parse_sheet_row(header_row, row)
                row_key = f"{form_data_temp.get('timestamp', '')}_{form_data_temp.get('responsible_email', '')}"
                
                if row_key not in processed_statuses:
                    print(f"\nTraitement de la ligne {i+2} (index {i})...")
                    process_form_response(header_row, row, credentials, pdf_handling_method)
                    processed_count += 1
                    time.sleep(5) # Pause entre chaque traitement
                else:
                    print(f"Ligne {i+2} (clé {row_key}) déjà traitée (Statut: {processed_statuses[row_key].get('status')}). Ignorée.")
            print(f"\nTraitement terminé. {processed_count} nouvelle(s) ligne(s) traitée(s).")
        else:
             # --- Traitement Simplifié: Juste la première ligne de données --- 
             print(f"Mode: Traitement de la première ligne de données uniquement (index 1).", flush=True) # flush=True pour Streamlit
             first_data_row = data_rows[0]
             # Passer la méthode PDF
             process_form_response(header_row, first_data_row, credentials, pdf_handling_method)
             # ----------------------------------------------------------------
        
        print("\nWorkflow terminé.")
        
    except Exception as e:
        print("\n*** ERREUR INATTENDUE DANS LE WORKFLOW PRINCIPAL ***")
        traceback.print_exc()

if __name__ == "__main__":
    # Logique pour exécuter depuis la ligne de commande (optionnel)
    # Par exemple, pour traiter toutes les lignes:
    # python main.py --run-all --pdf-method image
    import argparse
    parser = argparse.ArgumentParser(description="Lance le workflow d'évaluation ESCP.")
    parser.add_argument("--run-all", action="store_true", help="Traiter toutes les nouvelles lignes.")
    parser.add_argument("--pdf-method", choices=['direct', 'image'], default='direct', help="Méthode d'analyse PDF.")
    args = parser.parse_args()
    
    # Lancer main avec les arguments
    main(run_all=args.run_all, pdf_handling_method=args.pdf_method) 