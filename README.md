# ESCP Workflow - Interface Reviewer

Interface Streamlit pour le workflow d'analyse et de traitement des réponses au formulaire de suivi des projets financés par la Fondation ESCP.

## Installation

Utilisez Python **3.11** pour cette version. Les mises à jour de sécurité de
Streamlit et Pillow nécessitent au moins Python 3.11. NumPy est limité à 1.26.4
pour rester compatible avec le pandas 2.0.1 déjà utilisé par l'application.
PyArrow est fixé à 25.0.1 : la version 26 exige NumPy 2 et bloque le démarrage
avec ces versions de NumPy et pandas.

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

5. Configurez la connexion des responsables de revue dans le gestionnaire de
secrets de l'hébergeur ou dans `.streamlit/secrets.toml` en développement.
Le fichier `.streamlit/secrets.example.toml` fournit la structure à compléter.
Ne commitez jamais le fichier contenant les vrais secrets.

   - Créez un client OAuth Google de type application web, utilisant OpenID
     Connect, et configurez une URL de retour exacte :
     `https://VOTRE-DOMAINE/oauth2callback` en production,
     `http://localhost:8501/oauth2callback` uniquement en développement local.
   - Configurez `[auth]` et `[auth.google]` avec ce client et un secret de cookie
     aléatoire fort. Utilisez HTTPS en production.
   - Ajoutez les adresses Google complètes autorisées dans
     `[reviewer_auth].allowed_emails`. Une liste vide interdit tout accès.
   - Conservez séparément les secrets existants du compte de service Google.
     Le client OIDC identifie la personne ; le compte de service donne au
     serveur son accès aux fichiers et aux API Google.

À chaque exécution de l'interface, l'application exige une identité Google
vérifiée, une adresse autorisée et une identité non expirée. Les identifiants
du compte de service sont chargés seulement après cette vérification. Les
données de session sont effacées si l'identité change ou perd son accès.
Le bouton de déconnexion supprime aussi les données locales de la session.
Une déconnexion ne termine pas les autres onglets déjà ouverts ; leur identité
expire selon la date `exp` du jeton. Une action déjà lancée n'est pas interrompue
par cette vérification, qui a lieu à chaque nouvelle exécution de l'interface.

Les règles d'accès et secrets du serveur doivent être rechargés après une
modification de configuration. La suppression d'une adresse dans la liste
révoque son accès à la prochaine vérification avec cette configuration.

Avant de déployer : vérifier les parcours anonyme, compte Google non autorisé,
compte autorisé et déconnexion sur un environnement de test, puis tester la
lecture Sheets/Drive et la création de brouillons avec le compte de service.
Le secret du cookie et les secrets OAuth ne doivent pas être affichés ou logués.

Références : [connexion OIDC Streamlit](https://docs.streamlit.io/develop/api-reference/user/st.login)
et [identité et expiration](https://docs.streamlit.io/develop/api-reference/user/st.user).

## Lancement de l'application Streamlit

Pour lancer l'interface Streamlit:

```bash
cd escp_workflow
streamlit run streamlit_app.py
```

L'application sera disponible à l'adresse: http://localhost:8501

## Fonctionnalités

- **Authentification**: Connexion Google OIDC avec vérification de l'adresse,
  liste explicite des responsables de revue et contrôle de l'expiration
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

- Assurez-vous que le compte de service Google a accès uniquement aux Google
  Sheets et fichiers Drive nécessaires. La connexion d'un responsable de revue
  ne lui donne pas directement les identifiants de ce compte de service.
- Les fichiers téléchargés sont stockés dans le dossier `downloads/`
- Les logs et résultats sont stockés dans les fichiers `llm_interactions_log.md`, `generated_email_preview.html` et `internal_email_preview.html`

## Tests du contrôle d'accès

Ces tests utilisent uniquement la bibliothèque standard ; ils n'appellent
aucune API et ne chargent aucun identifiant réel :

```bash
python -m unittest discover -s tests -v
```
