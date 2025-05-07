import os
from dotenv import load_dotenv

# Charger les variables d'environnement depuis le fichier .env
load_dotenv()

# --- Clés API ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# --- Configuration Google ---
GOOGLE_FORM_ID = os.getenv("GOOGLE_FORM_ID")
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID") # Sera None si non défini dans .env
CREDENTIALS_FILE = os.getenv("CREDENTIALS_FILE", "credentials.json")
TOKEN_FILE = os.getenv("TOKEN_FILE", "token.json")

# Définir les scopes nécessaires pour les APIs Google
# Assurez-vous qu'ils correspondent à ceux définis dans la Google Cloud Console
SCOPES = [
    #"https://www.googleapis.com/auth/forms.responses.readonly", # Plus nécessaire si on passe par Sheets
    "https://www.googleapis.com/auth/drive.readonly",
    # "https://www.googleapis.com/auth/gmail.send", # Remplacé par compose
    "https://www.googleapis.com/auth/gmail.compose", # Pour créer des brouillons
    # Ajoutez le scope sheets si vous l'utilisez
    "https://www.googleapis.com/auth/spreadsheets.readonly",
]

# --- Configuration Email ---
SENDER_EMAIL = os.getenv("SENDER_EMAIL")
INTERNAL_REVIEW_EMAIL = os.getenv("INTERNAL_REVIEW_EMAIL")

# Vérifications simples
if not OPENAI_API_KEY:
    raise ValueError("La clé API OpenAI (OPENAI_API_KEY) n'est pas définie dans le fichier .env")
if not GOOGLE_FORM_ID:
    # Pour l'instant, on le garde optionnel si on passe par Sheets
    print("WARN: GOOGLE_FORM_ID n'est pas défini. Assurez-vous que GOOGLE_SHEET_ID est défini si nécessaire.")
    # raise ValueError("L'ID du Google Form (GOOGLE_FORM_ID) n'est pas défini dans le fichier .env")
if not SENDER_EMAIL:
    raise ValueError("L'adresse email d'envoi (SENDER_EMAIL) n'est pas définie dans le fichier .env")
if not INTERNAL_REVIEW_EMAIL:
    print("WARN: INTERNAL_REVIEW_EMAIL n'est pas défini. Le brouillon interne ne sera pas créé.")

print("Configuration chargée.") 