# ESCP Workflow - Interface Reviewer

Interface Streamlit pour le workflow d'analyse et de traitement des réponses au formulaire de suivi des projets financés par la Fondation ESCP.

## Installation

1. Clonez ce dépôt:
```bash
git clone <url-du-repo>
cd escp_workflow
```

2. Installez les dépendances:
```bash
pip install -r requirements.txt
```

3. Installez Poppler (nécessaire pour pdf2image):
   - **macOS**: `brew install poppler`
   - **Ubuntu/Debian**: `sudo apt-get install poppler-utils`
   - **Windows**: Téléchargez les binaires depuis [poppler-windows](https://github.com/oschwartz10612/poppler-windows/releases/) et ajoutez-les au PATH

4. Configurez les variables d'environnement:
   - Créez un fichier `.env` à la racine du projet avec les informations suivantes:
```
OPENAI_API_KEY=your_openai_api_key
GOOGLE_SHEET_ID=your_google_sheet_id
INTERNAL_REVIEW_EMAIL=email_for_internal_reviews@example.com
```

## Lancement de l'application Streamlit

Pour lancer l'interface Streamlit:

```bash
cd escp_workflow
streamlit run streamlit_app.py
```

L'application sera disponible à l'adresse: http://localhost:8501

## Fonctionnalités

- **Authentification**: Connexion avec un compte Google autorisé
- **Visualisation**: Affichage des réponses au formulaire avec possibilité de filtrage
- **Traitement**: Lancement du workflow d'analyse pour une réponse sélectionnée
- **Suivi**: Affichage des logs en temps réel pendant le traitement
- **Résultats**: Visualisation des emails générés (demandeur et interne)
- **Historique**: Suivi du statut des réponses traitées

## Workflow de traitement

1. Récupération des données du formulaire Google Sheet
2. Téléchargement des fichiers joints (budget et pièces justificatives)
3. Analyse du budget Excel
4. Analyse des pièces justificatives avec OpenAI
5. Évaluation globale du dossier
6. Génération d'emails pour le demandeur et l'équipe interne
7. Création de brouillons dans Gmail

## Notes importantes

- Assurez-vous que le compte Google utilisé a accès à la Google Sheet et aux fichiers Drive associés
- La première utilisation nécessite une autorisation OAuth pour accéder à l'API Google
- Les fichiers téléchargés sont stockés dans le dossier `downloads/`
- Les logs et résultats sont stockés dans les fichiers `llm_interactions_log.md`, `generated_email_preview.html` et `internal_email_preview.html` 