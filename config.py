import os
import streamlit as st
# from dotenv import load_dotenv # dotenv sera chargé conditionnellement

# Nom du secret Streamlit contenant les infos du compte de service GCP (dictionnaire)
GCP_SERVICE_ACCOUNT_SECRET_NAME = "gcp_service_account"
# Chemin local vers le fichier de clé du compte de service GCP (pour développement)
# La valeur par défaut est "service_account.json", vous pouvez la surcharger avec une variable d'env
DEFAULT_LOCAL_GCP_SA_FILE = "service_account.json"

# Essayer de charger depuis st.secrets (pour le déploiement Streamlit)
try:
    # st.secrets existe-t-il et la clé est-elle présente?
    if hasattr(st, 'secrets') and GCP_SERVICE_ACCOUNT_SECRET_NAME in st.secrets:
        GCP_SERVICE_ACCOUNT_INFO = st.secrets[GCP_SERVICE_ACCOUNT_SECRET_NAME]
        print(f"Informations du compte de service GCP chargées depuis st.secrets[{GCP_SERVICE_ACCOUNT_SECRET_NAME}]")
    else:
        GCP_SERVICE_ACCOUNT_INFO = None

    OPENAI_API_KEY = st.secrets.get("OPENAI_API_KEY") if hasattr(st, 'secrets') else None
    GOOGLE_FORM_ID = st.secrets.get("GOOGLE_FORM_ID") if hasattr(st, 'secrets') else None
    GOOGLE_SHEET_ID = st.secrets.get("GOOGLE_SHEET_ID") if hasattr(st, 'secrets') else None
    SENDER_EMAIL = st.secrets.get("SENDER_EMAIL") if hasattr(st, 'secrets') else None
    INTERNAL_REVIEW_EMAIL = st.secrets.get("INTERNAL_REVIEW_EMAIL") if hasattr(st, 'secrets') else None

    # Si une des clés principales est manquante après avoir essayé st.secrets, on passe au .env local
    # ou si GCP_SERVICE_ACCOUNT_INFO n'a pas été trouvé dans st.secrets
    if not OPENAI_API_KEY or not GCP_SERVICE_ACCOUNT_INFO: # Ajoutez d'autres conditions si nécessaire
        # Forcer le chargement depuis .env si on n'est pas dans un contexte Streamlit complet
        # ou si les secrets Streamlit ne sont pas complets
        if GCP_SERVICE_ACCOUNT_INFO is None : # Surtout si le SA n'est pas dans st.secrets
            print("Tentative de chargement de la configuration depuis les variables d'environnement locales / .env ...")
            raise KeyError # Déclenche le bloc except pour charger depuis .env

except (KeyError, AttributeError): # AttributeError si st.secrets n'existe pas
    print("Configuration via st.secrets échouée ou incomplète, chargement depuis .env / variables d'environnement locales.")
    from dotenv import load_dotenv
    load_dotenv()

    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    GOOGLE_FORM_ID = os.getenv("GOOGLE_FORM_ID")
    GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
    SENDER_EMAIL = os.getenv("SENDER_EMAIL")
    INTERNAL_REVIEW_EMAIL = os.getenv("INTERNAL_REVIEW_EMAIL")
    
    # Pour le compte de service en local
    LOCAL_GCP_SERVICE_ACCOUNT_FILE_PATH = os.getenv("LOCAL_GCP_SERVICE_ACCOUNT_FILE_PATH", DEFAULT_LOCAL_GCP_SA_FILE)
    GCP_SERVICE_ACCOUNT_INFO = None # Sera chargé depuis le fichier dans google_clients.py si ce chemin est utilisé

# Définir les scopes nécessaires pour les APIs Google
# Assurez-vous qu'ils correspondent à ceux définis dans la Google Cloud Console
SCOPES = [
    #"https://www.googleapis.com/auth/forms.responses.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/spreadsheets", # Ajout pour la création/modification
    "https://www.googleapis.com/auth/drive" # Ajout pour la gestion des permissions
]

# Vérifications simples
if not OPENAI_API_KEY:
    # Modifiez le message si vous ne voulez pas d'erreur bloquante ici
    print("WARN: La clé API OpenAI (OPENAI_API_KEY) n'est pas définie.") 
    # raise ValueError("La clé API OpenAI (OPENAI_API_KEY) n'est pas définie.")
# GCP_SERVICE_ACCOUNT_INFO est vérifié dans get_google_credentials
# if not GOOGLE_FORM_ID: # Commenté car peut être optionnel
#     print("WARN: GOOGLE_FORM_ID n'est pas défini. Assurez-vous que GOOGLE_SHEET_ID est défini si nécessaire.")
if not SENDER_EMAIL:
    # Modifiez le message si vous ne voulez pas d'erreur bloquante ici
    print("WARN: L'adresse email d'envoi (SENDER_EMAIL) n'est pas définie.")
    # raise ValueError("L'adresse email d'envoi (SENDER_EMAIL) n'est pas définie.")
# if not INTERNAL_REVIEW_EMAIL: # Commenté car peut être optionnel
#     print("WARN: INTERNAL_REVIEW_EMAIL n'est pas défini. Le brouillon interne ne sera pas créé.")

print("Configuration chargée.")
# Les variables disponibles après ce script sont:
# OPENAI_API_KEY, GOOGLE_FORM_ID, GOOGLE_SHEET_ID, SENDER_EMAIL, INTERNAL_REVIEW_EMAIL,
# GCP_SERVICE_ACCOUNT_SECRET_NAME (nom du secret), 
# GCP_SERVICE_ACCOUNT_INFO (dictionnaire des infos SA si via st.secrets, sinon None),
# LOCAL_GCP_SERVICE_ACCOUNT_FILE_PATH (chemin fichier local si pas via st.secrets),
# SCOPES 