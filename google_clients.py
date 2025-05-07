import os.path
import pickle # Alternative pour token.json si besoin, mais credentials est mieux
import re # Pour extraire l'ID du fichier Drive
import io # Pour télécharger les fichiers en mémoire
from typing import Union # <<< AJOUT pour compatibilité Python < 3.10
import traceback # Pour un meilleur affichage des erreurs

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload # Pour le téléchargement Drive

# Nouveaux imports pour Gmail
import base64
from email.mime.text import MIMEText
# Nouveaux imports pour les pièces jointes
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import mimetypes

# Importer la configuration
from config import SCOPES, CREDENTIALS_FILE, TOKEN_FILE, GOOGLE_FORM_ID, GOOGLE_SHEET_ID, SENDER_EMAIL

def get_google_credentials():
    """Gère le flux d'authentification OAuth 2.0 pour les APIs Google.

    Tente de charger les identifiants depuis TOKEN_FILE.
    Si invalides ou absents, lance le flux d'autorisation via le navigateur.
    Sauvegarde les nouveaux identifiants dans TOKEN_FILE.

    Returns:
        google.oauth2.credentials.Credentials: Les identifiants valides.
    """
    creds = None
    # Le fichier token.json stocke les jetons d'accès et de rafraîchissement de l'utilisateur.
    # Il est créé automatiquement lors de la première autorisation.
    if os.path.exists(TOKEN_FILE):
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
            print(f"Identifiants chargés depuis {TOKEN_FILE}")
        except Exception as e:
            print(f"Erreur lors du chargement de {TOKEN_FILE}: {e}. Tentative de ré-authentification.")
            creds = None # Forcer la ré-authentification

    # S'il n'y a pas d'identifiants (valides), laisser l'utilisateur se connecter.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("Les identifiants ont expiré, tentative de rafraîchissement...")
            try:
                creds.refresh(Request())
                print("Identifiants rafraîchis.")
            except Exception as e:
                print(f"Impossible de rafraîchir les identifiants: {e}")
                # Si le rafraîchissement échoue, on supprime le token et on relance le flux
                if os.path.exists(TOKEN_FILE):
                    os.remove(TOKEN_FILE)
                print(f"Ancien {TOKEN_FILE} supprimé. Veuillez vous ré-authentifier.")
                creds = None # Forcer la ré-authentification complète
        else:
            print(f"Aucun identifiant valide trouvé ou {TOKEN_FILE} absent.")
            print(f"Lancement du flux d'autorisation OAuth 2.0 en utilisant {CREDENTIALS_FILE}...")
            if not os.path.exists(CREDENTIALS_FILE):
                raise FileNotFoundError(f"Erreur: Le fichier d'identifiants {CREDENTIALS_FILE} est introuvable. Assurez-vous qu'il est au bon endroit.")
            try:
                flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
                # Note: port=0 permet de trouver un port libre automatiquement
                creds = flow.run_local_server(port=0)
                print("Authentification réussie.")
            except Exception as e:
                print(f"Erreur lors du flux d'authentification: {e}")
                # Potentiellement afficher plus d'aide ici, ex: vérifier l'URI de redirection dans GCP
                raise # Renvoyer l'erreur pour arrêter le script

        # Sauvegarder les identifiants pour la prochaine exécution
        try:
            with open(TOKEN_FILE, 'w') as token:
                token.write(creds.to_json())
            print(f"Identifiants sauvegardés dans {TOKEN_FILE}")
        except Exception as e:
             print(f"Attention: Impossible de sauvegarder les identifiants dans {TOKEN_FILE}: {e}")

    if not creds:
         raise RuntimeError("Impossible d'obtenir les identifiants Google.")

    return creds

# --- Fonctions pour les services spécifiques (à implémenter ensuite) ---

def get_forms_service(credentials):
    """Construit et retourne un client pour l'API Google Forms."""
    try:
        service = build('forms', 'v1', credentials=credentials)
        print("Service Google Forms initialisé.")
        return service
    except HttpError as error:
        print(f"Une erreur est survenue lors de la création du service Forms: {error}")
        return None

def get_drive_service(credentials):
    """Construit et retourne un client pour l'API Google Drive."""
    try:
        service = build('drive', 'v3', credentials=credentials)
        print("Service Google Drive initialisé.")
        return service
    except HttpError as error:
        print(f"Une erreur est survenue lors de la création du service Drive: {error}")
        return None

def get_sheets_service(credentials):
    """Construit et retourne un client pour l'API Google Sheets."""
    try:
        service = build('sheets', 'v4', credentials=credentials)
        print("Service Google Sheets initialisé.")
        return service
    except HttpError as error:
        print(f"Une erreur est survenue lors de la création du service Sheets: {error}")
        return None

def get_gmail_service(credentials):
    """Construit et retourne un client pour l'API Gmail."""
    try:
        service = build('gmail', 'v1', credentials=credentials)
        print("Service Gmail initialisé.")
        return service
    except HttpError as error:
        print(f"Une erreur est survenue lors de la création du service Gmail: {error}")
        return None

# --- Fonctions d'API spécifiques ---

# def get_form_responses(form_id: str, credentials):
#     """(DEPRECATED if using Sheets) Récupère toutes les réponses d'un Google Form spécifié."""
#     # ... (Code commenté ou supprimé)
#     pass # Fonction désactivée

def get_sheet_data(sheet_id: str, range_name: str, credentials):
    """Récupère les données d'une plage spécifiée dans une Google Sheet.

    Args:
        sheet_id: L'ID de la Google Sheet.
        range_name: La plage à lire (ex: 'Feuille 1!A:Z', 'Réponses au formulaire 1!A1:G').
                    Utiliser A:Z lit toutes les colonnes de la feuille par défaut.
        credentials: Les identifiants Google OAuth2 valides.

    Returns:
        list[list[str]]: Une liste de lignes, où chaque ligne est une liste de valeurs de cellules (str).
                         Retourne None en cas d'erreur.
    """
    sheets_service = get_sheets_service(credentials)
    if not sheets_service:
        return None

    try:
        print(f"Récupération des données depuis Sheet ID: {sheet_id}, Plage: {range_name}")
        result = sheets_service.spreadsheets().values().get(
            spreadsheetId=sheet_id,
            range=range_name
        ).execute()
        values = result.get('values', [])

        if not values:
            print('Aucune donnée trouvée.')
            return []
        else:
            print(f"{len(values)} lignes trouvées (y compris l'en-tête potentiel).")
            # On pourrait ajouter ici la logique pour ne traiter que les nouvelles lignes
            # en comparant avec un état précédent (ex: dernière ligne traitée).
            return values

    except HttpError as error:
        print(f"Une erreur HTTP est survenue lors de la récupération des données Sheets: {error}")
        error_details = error.resp.get('content', '{}')
        print(f"Détails de l'erreur: {error_details}")
        # Ex: Vérifier que l'ID de la feuille est correct et que le compte a accès.
        return None
    except Exception as e:
        print(f"Une erreur inattendue est survenue lors de la lecture Sheets: {e}")
        traceback.print_exc()
        return None

def extract_drive_file_id(url: str) -> Union[str, None]:
    """Extrait l'ID d'un fichier Google Drive depuis une URL.

    Args:
        url: L'URL Google Drive (ex: 'https://drive.google.com/open?id=FILE_ID').

    Returns:
        L'ID du fichier ou None si non trouvé.
    """
    # Essayer plusieurs patterns courants pour l'ID
    patterns = [
        r"id=([a-zA-Z0-9_-]+)",                   # Standard open?id=...
        r"/d/([a-zA-Z0-9_-]+)/",                  # /d/FILE_ID/
        r"/file/d/([a-zA-Z0-9_-]+)/",            # /file/d/FILE_ID/
        r"uc\?id=([a-zA-Z0-9_-]+)",               # uc?id=...
        r"open\?id=([a-zA-Z0-9_-]+)",             # open?id=... (redondant mais sûr)
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            print(f"ID extrait: {match.group(1)} de l'URL: {url}")
            return match.group(1)
    print(f"WARN: Impossible d'extraire l'ID de fichier Drive de l'URL: {url}")
    return None

def download_drive_file(file_id: str, credentials, destination_folder: str = "downloads") -> Union[str, None]:
    """Télécharge un fichier depuis Google Drive par son ID.

    Args:
        file_id: L'ID du fichier Google Drive.
        credentials: Les identifiants Google OAuth2 valides.
        destination_folder: Le dossier local où sauvegarder le fichier.

    Returns:
        Le chemin complet du fichier téléchargé, ou None en cas d'erreur.
    """
    drive_service = get_drive_service(credentials)
    if not drive_service:
        return None

    try:
        print(f"Tentative de téléchargement du fichier ID: {file_id}")
        # 1. Obtenir les métadonnées pour avoir le nom original du fichier
        file_metadata = drive_service.files().get(fileId=file_id, fields='name, mimeType').execute()
        file_name = file_metadata.get('name', f"{file_id}_downloaded")
        mime_type = file_metadata.get('mimeType')
        print(f"  Nom du fichier: {file_name}, Type MIME: {mime_type}")

        # Gérer les types Google Workspace (Docs, Sheets, Slides) qui nécessitent une exportation
        # Mime types: https://developers.google.com/drive/api/guides/mime-types
        export_mime_type = None
        if mime_type == 'application/vnd.google-apps.document':
            export_mime_type = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
            file_name += '.docx'
        elif mime_type == 'application/vnd.google-apps.spreadsheet':
            export_mime_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            file_name += '.xlsx'
        elif mime_type == 'application/vnd.google-apps.presentation':
            export_mime_type = 'application/vnd.openxmlformats-officedocument.presentationml.presentation'
            file_name += '.pptx'
        elif mime_type == 'application/vnd.google-apps.form':
             print(f"WARN: Le téléchargement direct des Google Forms (ID: {file_id}) n'est pas supporté via download.")
             return None # On ne peut pas 'télécharger' un Form comme un fichier binaire

        # Créer le dossier de destination s'il n'existe pas
        os.makedirs(destination_folder, exist_ok=True)
        destination_path = os.path.join(destination_folder, file_name)

        # 2. Préparer la requête de téléchargement (export ou download)
        if export_mime_type:
            print(f"  Exportation en tant que {export_mime_type}...")
            request = drive_service.files().export_media(fileId=file_id, mimeType=export_mime_type)
        else:
            print("  Téléchargement direct...")
            request = drive_service.files().get_media(fileId=file_id)

        # 3. Exécuter le téléchargement
        fh = io.FileIO(destination_path, 'wb') # Ouvrir le fichier local en écriture binaire
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while done is False:
            status, done = downloader.next_chunk()
            print(f"  Progression du téléchargement: {int(status.progress() * 100)}%")

        print(f"Fichier téléchargé avec succès : {destination_path}")
        return destination_path

    except HttpError as error:
        print(f"Une erreur HTTP est survenue lors du téléchargement du fichier {file_id}: {error}")
        error_details = error.resp.get('content', '{}')
        print(f"Détails de l'erreur: {error_details}")
        # Ex: Erreur 404 si le fichier n'existe pas/plus, 403 si pas les droits
        return None
    except Exception as e:
        print(f"Une erreur inattendue est survenue lors du téléchargement {file_id}: {e}")
        return None
    finally:
        if 'fh' in locals() and not fh.closed:
            fh.close()

# --- Nouvelle Fonction Gmail --- 
def create_gmail_draft(credentials, to: str, subject: str, message_html: str, attachment_paths: list = None):
    """Crée un brouillon d'email dans Gmail, avec pièces jointes optionnelles.

    Args:
        credentials: Les identifiants Google OAuth2 valides.
        to: Adresse email du destinataire.
        subject: Sujet de l'email.
        message_html: Corps de l'email au format HTML.
        attachment_paths: Liste des chemins vers les fichiers à joindre (optionnel).

    Returns:
        dict: L'objet Draft créé par l'API Gmail, ou None en cas d'erreur.
    """
    gmail_service = get_gmail_service(credentials)
    if not gmail_service:
        return None

    try:
        if attachment_paths:
            # --- Créer un message multipart si pièces jointes --- 
            mime_message = MIMEMultipart('mixed')
            mime_message['to'] = to
            mime_message['subject'] = subject

            # Ajouter le corps HTML
            html_part = MIMEText(message_html, 'html')
            mime_message.attach(html_part)

            # Ajouter les pièces jointes
            for file_path in attachment_paths:
                if not os.path.exists(file_path):
                    print(f"WARN: Fichier pièce jointe introuvable: {file_path}. Ignoré.")
                    continue
                
                content_type, encoding = mimetypes.guess_type(file_path)
                if content_type is None or encoding is not None:
                    content_type = 'application/octet-stream' # Type par défaut
                main_type, sub_type = content_type.split('/', 1)
                
                print(f"Ajout de la pièce jointe: {os.path.basename(file_path)} (Type: {content_type})")
                
                with open(file_path, 'rb') as fp:
                    if main_type == 'text':
                        # Pour les fichiers texte (comme .md), on peut utiliser MIMEText
                        # Lire avec encodage utf-8
                        try:
                             with open(file_path, 'r', encoding='utf-8') as f_text:
                                  msg_attach = MIMEText(f_text.read(), _subtype=sub_type, _charset='utf-8')
                        except Exception:
                             # Fallback si lecture texte échoue
                             fp.seek(0) # Revenir au début du fichier
                             msg_attach = MIMEBase(main_type, sub_type)
                             msg_attach.set_payload(fp.read())
                             encoders.encode_base64(msg_attach)
                    else:
                        # Pour les autres types, utiliser MIMEBase
                        msg_attach = MIMEBase(main_type, sub_type)
                        msg_attach.set_payload(fp.read())
                        # Encoder en Base64 pour le transport email
                        encoders.encode_base64(msg_attach)
                
                # Ajouter l'en-tête Content-Disposition
                filename = os.path.basename(file_path)
                msg_attach.add_header('Content-Disposition', 'attachment', filename=filename)
                mime_message.attach(msg_attach)
            
            # Encoder le message multipart complet
            encoded_message = base64.urlsafe_b64encode(mime_message.as_bytes()).decode()

        else:
            # --- Message simple si pas de pièce jointe (logique précédente) ---
            mime_message = MIMEText(message_html, 'html')
            mime_message['to'] = to
            mime_message['subject'] = subject
            encoded_message = base64.urlsafe_b64encode(mime_message.as_bytes()).decode()

        # Créer le corps de la requête API
        create_message = {
            'message': {
                'raw': encoded_message
            }
        }

        # Appeler l'API
        draft = gmail_service.users().drafts().create(userId='me', body=create_message).execute()

        print(f"Brouillon créé avec succès pour {to}. ID: {draft['id']}")
        if attachment_paths:
            print(f"  -> Avec {len(attachment_paths)} pièce(s) jointe(s).")
        return draft

    except HttpError as error:
        print(f"Une erreur HTTP est survenue lors de la création du brouillon: {error}")
        error_details = error.resp.get('content', '{}')
        print(f"Détails de l'erreur: {error_details}")
        return None
    except Exception as e:
        print(f"Une erreur inattendue est survenue lors de la création du brouillon: {e}")
        traceback.print_exc()
        return None

# Exemple d'utilisation (mis à jour pour tester PJ)
if __name__ == '__main__':
    # Import SENDER_EMAIL spécifiquement pour le test
    from config import SENDER_EMAIL
    
    print("Tentative d'obtention des identifiants Google...")
    sheet_data = None
    creds = None
    try:
        # Rappel: Supprimer token.json si les SCOPES ont changé (ajout de sheets.readonly)
        if not os.path.exists(TOKEN_FILE):
             print(f"INFO: {TOKEN_FILE} non trouvé. Une nouvelle autorisation sera demandée.")
        elif SCOPES != Credentials.from_authorized_user_file(TOKEN_FILE).scopes:
             print(f"WARN: Les scopes requis ont changé. Suppression de {TOKEN_FILE} pour redemander l'autorisation.")
             os.remove(TOKEN_FILE)

        creds = get_google_credentials()
        print("Identifiants obtenus avec succès.")

        # --- Test Récupération Données Sheets --- 
        if GOOGLE_SHEET_ID:
            print("\n--- Test de récupération des données Sheets ---")
            # !! IMPORTANT: Adaptez le nom de la feuille si nécessaire !!
            # Si la feuille créée s'appelle "Réponses au formulaire 1", utilisez "'Réponses au formulaire 1'!A:Z"
            # Si elle s'appelle "Sheet1", utilisez "Sheet1!A:Z"
            # Les apostrophes sont nécessaires si le nom contient des espaces.
            # A:Z lit toutes les colonnes.
            sheet_range = "responses!A:Z" # <<< ADAPTEZ CE NOM/PLAGE
            print(f"Lecture de la plage : {sheet_range}")
            sheet_data = get_sheet_data(GOOGLE_SHEET_ID, sheet_range, creds)

            if sheet_data:
                header_row = sheet_data[0]
                print(f"\nEn-tête de la feuille: {header_row}")
                # Identifier les index des colonnes contenant les URLs des fichiers
                # Remplacez les noms par ceux de VOS colonnes d'upload
                budget_url_col_name = "Download the realised budget of the project" # <<< ADAPTEZ
                receipts_url_col_name = "Please upload your files here"          # <<< ADAPTEZ
                try:
                    budget_col_index = header_row.index(budget_url_col_name)
                    print(f"-> Colonne Budget URL trouvée à l'index: {budget_col_index}")
                except ValueError:
                    budget_col_index = -1
                    print(f"WARN: Colonne '{budget_url_col_name}' non trouvée dans l'en-tête.")
                try:
                    receipts_col_index = header_row.index(receipts_url_col_name)
                    print(f"-> Colonne Reçus URLs trouvée à l'index: {receipts_col_index}")
                except ValueError:
                    receipts_col_index = -1
                    print(f"WARN: Colonne '{receipts_url_col_name}' non trouvée dans l'en-tête.")

                # Traiter la première ligne de données (après l'en-tête) pour le test
                if len(sheet_data) > 1:
                    first_data_row = sheet_data[1]
                    print(f"\nTraitement de la première ligne de données: {first_data_row[:5]}...") # Affiche les 5 premières colonnes

                    urls_to_process = []
                    if budget_col_index != -1 and len(first_data_row) > budget_col_index:
                        budget_urls = first_data_row[budget_col_index]
                        if budget_urls: # Peut contenir plusieurs URLs séparées par des virgules
                             urls_to_process.extend([url.strip() for url in budget_urls.split(',')])

                    if receipts_col_index != -1 and len(first_data_row) > receipts_col_index:
                        receipts_urls = first_data_row[receipts_col_index]
                        if receipts_urls: # Peut contenir plusieurs URLs séparées par des virgules
                             urls_to_process.extend([url.strip() for url in receipts_urls.split(',')])

                    print(f"\nURLs à traiter pour la première ligne: {urls_to_process}")

                    # --- Test Extraction ID et Téléchargement --- 
                    print("\n--- Test Extraction ID & Téléchargement (depuis URLs Sheet) --- ")
                    download_success = False
                    if not urls_to_process:
                         print("Aucune URL trouvée dans les colonnes spécifiées pour la première ligne de données.")

                    for url in urls_to_process:
                        if not url:
                            continue
                        print(f"\nTraitement URL: {url}")
                        file_id = extract_drive_file_id(url)
                        if file_id:
                            downloaded_path = download_drive_file(file_id, creds)
                            if downloaded_path:
                                print(f"Téléchargement réussi: {downloaded_path}")
                                download_success = True
                                # On peut s'arrêter après le premier succès pour le test
                                # break
                            else:
                                print(f"Échec du téléchargement pour fileId: {file_id} (URL: {url})")
                        else:
                             print(f"Impossible d'extraire un fileId de l'URL: {url}")
                    
                    if download_success:
                         print("\nAu moins un fichier a été téléchargé avec succès depuis les URLs de la feuille.")
                    elif urls_to_process:
                         print("\nAucun fichier n'a pu être téléchargé depuis les URLs trouvées.")

                else:
                    print("\nAucune ligne de données trouvée (seulement l'en-tête).")
            else:
                print("Échec de la récupération des données Sheets ou feuille vide.")

        else:
            print("\nSkipping sheet data test: GOOGLE_SHEET_ID non défini.")
        # --- Fin Test Récupération Données Sheets ---

        # --- Test final Initialisation Services --- 
        print("\n--- Test final Initialisation Services ---")
        # Test de création des services (on s'assure qu'ils sont toujours initialisables)
        if creds:
            forms_service = get_forms_service(creds)
            drive_service = get_drive_service(creds)
            sheets_service = get_sheets_service(creds)
            gmail_service = get_gmail_service(creds)

            if all([forms_service, drive_service, sheets_service, gmail_service]):
                print("Tous les services Google ont été initialisés avec succès (vérification finale)." )
            else:
                print("Au moins un service Google n'a pas pu être initialisé (vérification finale).")
        else:
             print("Impossible de vérifier l'initialisation des services car les identifiants (creds) sont manquants.")
        # --- Fin Test Initialisation --- 

        # --- Nouveau Test: Brouillon avec Pièce Jointe --- 
        print("\n--- Test Création Brouillon Gmail AVEC Pièce Jointe --- ")
        test_recipient = SENDER_EMAIL # Envoyer à soi-même
        if test_recipient:
            # Créer un fichier de test pour la PJ
            test_attachment_file = "test_log_attachment.txt"
            with open(test_attachment_file, "w") as f_attach:
                f_attach.write("Ceci est le contenu du fichier de log de test.\nLigne 2.")
            print(f"Fichier PJ de test créé: {test_attachment_file}")
            
            test_subject_pj = "Test Brouillon ESCP AVEC PJ"
            test_body_html_pj = "<h1>Test Pièce Jointe</h1><p>Cet email devrait contenir un fichier .txt en pièce jointe.</p>"
            
            draft_result_pj = create_gmail_draft(
                creds, 
                test_recipient, 
                test_subject_pj, 
                test_body_html_pj, 
                attachment_paths=[test_attachment_file] # Passer le chemin du fichier
            )
            if draft_result_pj:
                print("Vérifiez votre dossier Brouillons dans Gmail pour l'email avec PJ.")
            else:
                print("Échec de la création du brouillon avec PJ.")
                
            # Nettoyage du fichier de test
            # try:
            #     os.remove(test_attachment_file)
            # except OSError:
            #     pass
        else:
            print("WARN: SENDER_EMAIL non défini, impossible de tester le brouillon avec PJ.")
        # --- Fin Test Brouillon --- 

    except FileNotFoundError as fnf_error:
        print(f"Erreur Fichier Non Trouvé: {fnf_error}")
        traceback.print_exc()
    except Exception as e:
        # Affichage amélioré pour toute autre exception
        print(f"\\n*** Une erreur générale et inattendue est survenue ! ***")
        print(f"  Type d'erreur: {type(e)}")
        print(f"  Message d'erreur: {e}")
        print("  Traceback complet:")
        traceback.print_exc() # Affiche la pile d'appels complète 