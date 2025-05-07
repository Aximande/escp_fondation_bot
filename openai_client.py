import os
import base64
import json
import mimetypes
from openai import OpenAI # Correction: Importer directement OpenAI
import traceback
from io import BytesIO

# Importer la configuration (pour la clé API)
from config import OPENAI_API_KEY

# Essayer d'importer pdf2image, mais ne pas planter si absent
pdf2image_installed = False
try:
    from pdf2image import convert_from_path
    pdf2image_installed = True
    print("INFO: Module pdf2image trouvé.")
except ImportError:
    print("WARN: Module pdf2image non trouvé. L'option d'analyse PDF via image ne sera pas disponible.")
    print("      Pour l'activer, installez pdf2image (pip install pdf2image) et poppler.")

# Initialiser le client OpenAI globalement
# Il est recommandé de gérer les erreurs ici si la clé manque
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY n'est pas définie dans le fichier .env")

try:
    client = OpenAI(api_key=OPENAI_API_KEY)
    print("Client OpenAI initialisé.")
except Exception as e:
    print(f"Erreur lors de l'initialisation du client OpenAI: {e}")
    client = None

# --- Constantes pour les prompts (Analyse Justificatifs) ---
PROMPT_INSTRUCTIONS_SUPPORTING_DOC = """
Vous êtes un expert en analyse de documents pour la Fondation ESCP. Votre rôle est d'examiner les pièces justificatives (factures, contrats, photos, etc.) soumises par les bénéficiaires de subventions pour vérifier leur authenticité, pertinence et conformité.

Pour chaque document, vous devez:
1. Identifier le type de document (facture, contrat, photo d'activité, etc.)
2. Extraire les informations financières pertinentes (montants, dates, parties impliquées)
3. Vérifier que le document est daté de 2025
4. Évaluer la lisibilité et la qualité du document
5. Déterminer la pertinence du document par rapport au projet déclaré
"""

PROMPT_MESSAGE_SUPPORTING_DOC = """
Analyse cette pièce justificative pour un projet financé par la Fondation ESCP.

Informations du projet:
- Nom du projet: {project_name}
- Description: {project_description}
- Catégories de dépenses déclarées: {expense_categories}

Examine ce document (fourni sous forme d'image ou de texte) et identifie:
1. Type de document (facture, contrat, photo d'activité, liste de bénéficiaires, etc.)
2. Montants financiers mentionnés et période concernée
3. Parties impliquées (personnes, organisations)
4. Qualité/lisibilité du document (bonne, moyenne, mauvaise)
5. Est-ce que ce document semble authentique et pertinent pour ce projet?

Fournis ton analyse au format JSON, en respectant STRICTEMENT la structure suivante sans AUCUN texte avant ou après:

{json_format}
"""

JSON_FORMAT_SUPPORTING_DOC = """
{
  "document_type": "",
  "financial_amounts": [],
  "date_period": "",
  "in_2025": true|false,
  "parties_involved": [],
  "quality": "high|medium|low",
  "authenticity": "high|medium|low",
  "relevance": "high|medium|low",
  "issues_identified": [],
  "conclusion": ""
}
"""

# --- Constantes pour les prompts (Évaluation Globale) ---
PROMPT_INSTRUCTIONS_OVERALL_ASSESSMENT = """
Vous êtes un expert en évaluation de dossiers pour la Fondation ESCP. Votre rôle est d'analyser l'ensemble d'un dossier de justification d'utilisation de fonds pour déterminer sa complétude, sa conformité et sa cohérence, en allant au-delà d'une simple synthèse.

Vous devez examiner de manière critique et approfondie:
1. Les données du formulaire soumis par le bénéficiaire.
2. Le résultat de l'analyse automatisée (Python) du fichier budget Excel (calculs, dates, cohérence interne).
3. Les résultats des analyses par IA (GPT-4o) de chaque pièce justificative individuelle.
4. La cohérence globale entre toutes ces sources d'information.

**Votre analyse doit spécifiquement inclure:**
*   **Vérification Croisée Détaillée:** Comparez activement les dépenses listées dans l'Excel détaillé avec les informations (montants, descriptions, dates) des pièces justificatives fournies. Signalez toute dépense non justifiée ou justifiée par un document non pertinent.
*   **Identification de "Red Flags":** Relevez tout élément suspect ou nécessitant une attention particulière (ex: dépenses hors périmètre, justifications vagues, formats de documents inhabituels, incohérences répétées, montants élevés non étayés).
*   **Synthèse Critique:** Résumez non seulement les faits mais aussi votre *interprétation* des forces et faiblesses du dossier.

Fournissez une évaluation structurée avec une décision claire (APPROUVÉ, INFORMATIONS COMPLÉMENTAIRES, INCOMPLET) et une justification DÉTAILLÉE.
Votre réponse finale doit IMPÉRATIVEMENT être au format JSON spécifié, sans aucun texte avant ou après.
"""

PROMPT_MESSAGE_OVERALL_ASSESSMENT = """
Évalue ce dossier complet de rapport d'utilisation de fonds pour la Fondation ESCP en te basant sur TOUTES les informations fournies ci-dessous et en suivant les instructions système pour une analyse critique.

1. DONNÉES DU FORMULAIRE (déclaratif utilisateur):
```json
{form_data_json}
```

2. ANALYSE AUTOMATISÉE DU FICHIER BUDGET EXCEL (via script Python):
```json
{budget_analysis_json}
```

3. ANALYSES INDIVIDUELLES DES PIÈCES JUSTIFICATIVES (via GPT-4o):
```json
{documents_analysis_json}
```

INSTRUCTIONS SPÉCIFIQUES POUR TON ANALYSE APPROFONDIE:
- Effectue la **vérification croisée** entre les dépenses détaillées de l'analyse budget (si disponible) et les montants/descriptions des pièces justificatives. Liste les dépenses non ou mal justifiées.
- Identifie les **"Red Flags"** potentiels (incohérences, dépenses suspectes, justifications faibles, etc.).
- Évalue si le montant total justifié par les pièces **valides et pertinentes** correspond au montant dépensé déclaré.
- Prends en compte TOUS les `issues_identified` des analyses précédentes.
- Formule une recommandation claire (APPROUVÉ, INFORMATIONS COMPLÉMENTAIRES, INCOMPLET).
- Rédige une **justification détaillée** expliquant clairement les raisons de ta décision, en mentionnant les preuves spécifiques.
- Si INFORMATIONS COMPLÉMENTAIRES ou INCOMPLET, liste précisément les éléments manquants ou points à clarifier.

Produis ta réponse finale au format JSON demandé ci-dessous, sans aucun texte additionnel avant ou après le JSON.

Format JSON attendu:
{json_format}
"""

JSON_FORMAT_OVERALL_ASSESSMENT = """
{
  "status": "APPROVED|NEEDS_MORE_INFO|INCOMPLETE",
  "summary_of_findings": "Synthèse très courte des points principaux (1-2 phrases max).",
  "detailed_justification": "Explication détaillée et argumentée de la décision finale, incluant les résultats de la vérification croisée et l'évaluation globale.",
  "red_flags": [
      "Description d'un point suspect ou red flag identifié 1",
      "Description d'un point suspect ou red flag identifié 2"
  ],
  "financial_assessment_ok": true|false,
  "documentation_assessment_ok": true|false,
  "missing_elements_or_clarifications": [
      "Description précise de l'élément manquant ou à clarifier 1",
      "Description précise de l'élément manquant ou à clarifier 2"
  ],
  "final_recommendation": "Recommandation claire basée sur le statut.",
  "suggested_email_template": "approval|additional_info|incomplete"
}
"""

# --- Constantes pour les prompts (Génération Email HTML Demandeur) ---
PROMPT_INSTRUCTIONS_APPLICANT_HTML_EMAIL = """
Tu es un assistant expert en rédaction de communications institutionnelles pour la Fondation ESCP. Ton rôle est de générer des emails HTML professionnels, élégants, responsives, et compatibles avec Gmail/Outlook, destinés au **porteur de projet**.
Tu utilises uniquement du HTML et du CSS inline simple.
Tu structures l'information de manière claire : statut mis en évidence, liste des actions requises si nécessaire.
**Crée un en-tête textuel simple et élégant** (ex: "ESCP Business School | Fondation") au lieu d'une image logo.
L'email doit être clair et concis pour le destinataire.
NE PAS inclure de commentaires dans le code HTML.
Produire UNIQUEMENT le code HTML complet, commençant par `<!DOCTYPE html>` et finissant par `</html>`.
"""

PROMPT_MESSAGE_APPLICANT_HTML_EMAIL = """
Génère le code HTML complet pour un email destiné au porteur de projet, basé sur l'évaluation suivante.

**Destinataire:** {responsible_name}
**Projet:** {project_name}

**Données d'évaluation Clés (JSON):**
```json
{assessment_data_json}
```

**Instructions pour le contenu de l'email:**

1.  **En-tête:** Crée un en-tête texte stylisé simple, par exemple `<div style="padding-bottom: 15px; margin-bottom: 20px; border-bottom: 1px solid #eee;"><span style="font-size: 18px; color: #003366; font-weight: bold;">ESCP Business School</span> | <span style="font-size: 16px; color: #555;">Fondation</span></div>`. Adapte le style si besoin.
2.  **Salutation:** S'adresser au destinataire (`responsible_name`).
3.  **Corps principal:**
    *   Remercier pour la soumission (`{project_name}`).
    *   Annoncer clairement le **statut** (`assessment_data.status`) avec style visuel (vert/jaune/rouge léger).
    *   Si **APPROUVÉ**: Confirmer et mentionner le paiement (`{remaining_amount}`).
    *   Si **INFORMATIONS COMPLÉMENTAIRES** ou **INCOMPLET**: Lister clairement les `assessment_data.missing_elements_or_clarifications` et inviter à agir.
    *   **NE PAS INCLURE** les détails internes de l'analyse budget ou PJ ici.
4.  **Conclusion et Pied de page:** Formule de politesse, Signature "L'équipe de la Fondation ESCP", Coordonnées.

**Contraintes Techniques:** HTML valide, CSS inline, responsive, lisible.

Produis **UNIQUEMENT** le code HTML complet.
"""

# --- Constantes pour les prompts (Génération Email HTML INTERNE) ---
PROMPT_INSTRUCTIONS_INTERNAL_HTML_EMAIL = """
Tu es un assistant d'analyse expert pour la Fondation ESCP. Ton rôle est de générer un **rapport HTML interne**, destiné à l'équipe de la Fondation, synthétisant l'évaluation complète d'un dossier de justification de fonds.
Le rapport doit être extrêmement clair, factuel, structuré, et **visuellement professionnel** pour une revue rapide et efficace.
Utilise uniquement HTML et CSS **inline**. Structure l'information avec des titres clairs (`<h2>`, `<h3>`), des paragraphes concis, des listes à puces (`<ul><li>`) et des **tableaux (`<table>`, `<th>`, `<tr>`, `<td>`)** pour présenter les données structurées (analyse budget, analyse PJ).
Utilise des **couleurs de fond discrètes** (ex: `#f2f2f2` pour les en-têtes de section, vert pâle/jaune pâle/rouge pâle pour le statut) et du **padding/margin** pour aérer le contenu.
**Crée un en-tête textuel simple et professionnel (ex: "ESCP Business School | Fondation") au lieu d'une image logo.
NE PAS inclure de commentaires dans le code HTML.
Produire UNIQUEMENT le code HTML complet, commençant par `<!DOCTYPE html>` et finissant par `</html>`.
"""

PROMPT_MESSAGE_INTERNAL_HTML_EMAIL = """
Génère le code HTML **complet** pour un rapport d'évaluation interne basé sur les données suivantes.

**Projet:** {project_name}
**Responsable:** {responsible_name}

**1. Données d'évaluation GLOBALE du dossier (JSON):**
```json
{assessment_data_json}
```

**2. Données de l'analyse détaillée du BUDGET EXCEL (par script Python) (JSON):**
```json
{budget_analysis_json}
```

**3. Données des analyses individuelles des PIÈCES JUSTIFICATIVES (par GPT-4o) (JSON Array):**
```json
{supporting_docs_json}
```

**Instructions spécifiques et structure du rapport HTML:**

1.  **En-tête OBLIGATOIRE :** Commence IMPÉRATIVEMENT par un en-tête TEXTE stylisé. **N'UTILISE PAS de balise `<img>` pour le logo.** Utilise un `<div>` comme ceci: `<div style="padding-bottom: 15px; margin-bottom: 20px; border-bottom: 1px solid #eee; font-size: 18px; color: #003366; font-weight: bold;">ESCP Business School | <span style=\"font-size: 16px; color: #555; font-weight: normal;\">Fondation</span></div>`
2.  **Titre Principal:** `<h1>Rapport d'Évaluation Interne - Projet: {project_name}</h1>`
3.  **Section Informations Générales:**
    *   Présenter clairement : Nom du responsable, Projet.
    *   Afficher le **Statut Final** (`assessment_data.status`) avec une mise en forme visuelle distincte (ex: `style="background-color: #f8d7da; color: #721c24; padding: 5px; border-radius: 3px;"` pour Incomplet, `#fff3cd; color: #856404;` pour Infos Comp., `#d4edda; color: #155724;` pour Approuvé).
    *   Afficher la **Recommandation Finale** (`assessment_data.final_recommendation`) en évidence.
4.  **Section Justification Détaillée & Red Flags:**
    *   Titre : `<h2>Analyse Approfondie et Points d'Attention</h2>`
    *   Inclure le contenu de `assessment_data.detailed_justification`.
    *   Si `assessment_data.red_flags` existent, les lister sous un sous-titre `<h3>Red Flags Identifiés</h3>` avec une liste à puces.
5.  **Section Analyse Détaillée du Budget:**
    *   Titre : `<h2>Analyse du Budget (Script Python)</h2>`
    *   Utiliser un **tableau HTML** (`<table>`) pour présenter les conclusions de `budget_analysis_json` de manière structurée (une ligne par point de vérification : Correspondance formulaire, Cohérence totaux Catégories/Détaillé, Dates 2025, Écarts >5%, Calcul Solde, Issues identifiées).
6.  **Section Analyse Approfondie des Pièces Justificatives:**
    *   Titre : `<h2>Analyse des Pièces Justificatives (IA)</h2>`
    *   Pour chaque document dans `supporting_docs_json`:
        *   Utiliser une **ligne de tableau** ou une sous-section `div` distincte.
        *   **Interpréter et commenter** la pertinence (`relevance`), l'authenticité (`authenticity`) et les problèmes (`issues_identified`) dans le contexte du projet et du budget.
        *   Mentionner les montants (`financial_amounts`) et la date (`date_period`, `in_2025`).
        *   Fournir une conclusion concise sur la validité/utilité de la pièce.
    *   Si la liste est vide, indiquer clairement "Aucune pièce justificative analysée".
7.  **Pied de page:** Simple ligne avec la date de génération.

**Contraintes Techniques:**
*   HTML valide, CSS **inline uniquement**, design **professionnel et épuré**.
*   Conteneur principal (`<div style="max-width: 800px; margin: auto; font-family: Arial, sans-serif; border: 1px solid #ccc; padding: 20px;">`).
*   Utiliser `padding` et `margin` généreusement pour la lisibilité.
*   Styles clairs pour les titres (`<h2>`, `<h3>`) et les tableaux (`<th style="background-color: #f2f2f2; text-align: left; padding: 8px;">`, `<td style="border-bottom: 1px solid #ddd; padding: 8px;">`).

Produis **UNIQUEMENT** le code HTML complet, en commençant par `<!DOCTYPE html>`.
"""

def encode_image_to_base64(image_path):
    """Encode une image en base64 pour l'API Vision."""
    try:
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
    except Exception as e:
        print(f"Erreur lors de l'encodage de l'image {image_path}: {e}")
        return None

def encode_pdf_to_base64(pdf_path):
    """Encode un fichier PDF en base64."""
    try:
        with open(pdf_path, "rb") as pdf_file:
            return base64.b64encode(pdf_file.read()).decode('utf-8')
    except Exception as e:
        print(f"Erreur lors de l'encodage du PDF {pdf_path}: {e}")
        return None

def analyse_supporting_document(file_path: str, project_context: dict, pdf_handling_method: str = 'direct'):
    """Analyse un fichier justificatif (image, PDF, texte) avec OpenAI.

    Args:
        file_path: Chemin vers le fichier justificatif.
        project_context: Dictionnaire contenant les infos du projet
                         (project_name, project_description, expense_categories).
        pdf_handling_method: 'direct' (envoie PDF encodé) ou 'image' (convertit en image).

    Returns:
        dict: Le résultat de l'analyse au format JSON, ou None en cas d'erreur.
    """
    if not client:
        print("ERREUR: Client OpenAI non initialisé.")
        return None

    print(f"\n--- Analyse OpenAI du document: {file_path} ---")
    mime_type, _ = mimetypes.guess_type(file_path)
    file_name = os.path.basename(file_path)
    is_image = mime_type and mime_type.startswith('image/')
    is_pdf = mime_type == 'application/pdf'

    # Préparer le message pour l'API
    message_content = []
    final_prompt = PROMPT_MESSAGE_SUPPORTING_DOC.format(
        project_name=project_context.get('project_name', 'N/A'),
        project_description=project_context.get('project_description', 'N/A'),
        expense_categories=project_context.get('expense_categories', 'N/A'),
        json_format=JSON_FORMAT_SUPPORTING_DOC
    )
    # Mettre le prompt texte en premier
    message_content.append({"type": "text", "text": final_prompt})

    # --- Logique de gestion de fichier MISE À JOUR AVEC OPTION PDF --- 
    model_to_use = "gpt-4o" 
    print(f"Utilisation du modèle: {model_to_use}")
    print(f"Méthode de traitement PDF sélectionnée: {pdf_handling_method}") # Log la méthode

    if is_image:
        print("Type de fichier détecté: Image. Encodage en base64...")
        base64_image = encode_image_to_base64(file_path)
        if base64_image:
            message_content.append({
                "type": "image_url",
                "image_url": {"url": f"data:{mime_type};base64,{base64_image}"}
            })
            print(f"Image encodée ajoutée au message.")
        else:
            print("ERREUR: Échec de l'encodage de l'image.")
            return None
            
    elif is_pdf:
        # Tenter la conversion image si demandée ET si pdf2image est installé
        if pdf_handling_method == 'image' and pdf2image_installed:
            print("Type de fichier détecté: PDF. Tentative de conversion en image (page 1)...")
            try:
                # Convertir seulement la première page en image PIL
                images = convert_from_path(file_path, first_page=1, last_page=1, fmt='png') # Nécessite poppler
                if images:
                    img_byte_arr = BytesIO()
                    images[0].save(img_byte_arr, format='PNG') # Sauver l'image PIL en bytes
                    img_byte_arr = img_byte_arr.getvalue()
                    base64_image_from_pdf = base64.b64encode(img_byte_arr).decode('utf-8')

                    message_content.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{base64_image_from_pdf}"}
                    })
                    print("PDF converti en image (page 1) et ajouté au message.")
                else:
                    print("ERREUR: pdf2image n'a retourné aucune image.")
                    # Fallback vers méthode directe si conversion échoue ? Ou retourner erreur ?
                    # Pour l'instant, on retourne une erreur structurée
                    return {
                         "document_type": "PDF (Erreur Conversion Image)",
                         "issues_identified": ["La conversion du PDF en image a échoué (pdf2image n'a rien retourné)."],
                         "conclusion": "Analyse non effectuée."
                    }
            except Exception as pdf_img_err:
                print(f"ERREUR lors de la conversion PDF en image: {pdf_img_err}")
                print(" -> Vérifiez si Poppler est installé et accessible dans le PATH.")
                # Fallback vers méthode directe si conversion échoue ? Ou retourner erreur structurée ?
                return {
                     "document_type": "PDF (Erreur Conversion Image)",
                     "issues_identified": [f"Erreur technique lors de la conversion PDF en image: {pdf_img_err}"],
                     "conclusion": "Analyse non effectuée."
                }
                
        elif pdf_handling_method == 'image' and not pdf2image_installed:
             print("WARN: Méthode PDF 'image' demandée mais pdf2image non installé. Utilisation de la méthode 'direct' à la place.")
             # Fallback vers méthode directe
             pdf_handling_method = 'direct' # Forcer la méthode directe, ou image si vous voulez passer
             
        # Exécuter la méthode directe si c'est la méthode par défaut/demandée ou si fallback
        if pdf_handling_method == 'direct':
            print("Type de fichier détecté: PDF. Encodage en base64 (méthode directe)...")
            base64_pdf = encode_pdf_to_base64(file_path)
            if base64_pdf:
                message_content.append({
                    "type": "file",
                    "file": {
                        "filename": file_name,
                        "file_data": f"data:{mime_type};base64,{base64_pdf}"
                    }
                })
                print(f"PDF encodé (méthode directe) ajouté au message.")
            else:
                 print("ERREUR: Échec de l'encodage du PDF.")
                 return None
             
    else: # Supposer fichier texte ou type inconnu
        print("Type de fichier détecté: Texte (ou inconnu lu comme texte).")
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                text_content = f.read()
            # Ajouter le contenu texte (potentiellement après le fichier si image/pdf déjà ajouté)
            message_content.append({"type": "text", "text": "\n\nCONTENU DU DOCUMENT TEXTE:\n" + text_content[:15000] }) # Limiter la taille
            print(f"Contenu texte lu et ajouté au message.")
        except Exception as e:
            print(f"ERREUR: Impossible de lire le fichier comme texte: {e}")
            message_content.append({"type":"text", "text":"\n\n[ERREUR: Impossible de lire le contenu texte de ce fichier.]"})

    # Appeler l'API OpenAI
    try:
        print("Envoi de la requête à l'API OpenAI...")
        response = client.chat.completions.create(
            model=model_to_use,
            messages=[
                {"role": "user", "content": message_content} # Envoyer tout le contenu
            ],
            temperature=0.2, 
            response_format={ "type": "json_object" } 
        )
        
        json_response_str = response.choices[0].message.content
        print("Réponse reçue d'OpenAI.")

        # Parser la réponse JSON
        try:
            analysis_json = json.loads(json_response_str)
            print("Réponse JSON parsée avec succès.")
            return analysis_json
        except json.JSONDecodeError as json_error:
            print(f"ERREUR: Impossible de parser la réponse JSON d'OpenAI: {json_error}")
            print(f"Réponse reçue: {json_response_str}")
            return {
                "document_type": "Erreur Analyse",
                "issues_identified": ["La réponse d'OpenAI n'était pas un JSON valide."],
                "conclusion": "Analyse échouée.",
                "raw_response": json_response_str
            }

    except Exception as e:
        print(f"ERREUR lors de l'appel à l'API OpenAI: {e}")
        traceback.print_exc()
        return None

# --- Fonction d'Évaluation Globale --- 
def assess_overall_dossier(form_data: dict, budget_analysis: dict, documents_analyses: list):
    """Évalue l'ensemble du dossier en utilisant GPT-4.1.

    Args:
        form_data: Dictionnaire des données du formulaire.
        budget_analysis: Dictionnaire résultat de l'analyse Excel (Python).
        documents_analyses: Liste des dictionnaires résultats de l'analyse
                             des pièces justificatives (GPT-4o).

    Returns:
        dict: Le JSON de l'évaluation finale, ou None en cas d'erreur.
    """
    if not client:
        print("ERREUR: Client OpenAI non initialisé.")
        return None

    print("\n--- Début de l'évaluation globale du dossier avec GPT-4.1 ---")

    # Préparer les données JSON pour le prompt
    try:
        form_data_json = json.dumps(form_data, indent=2, ensure_ascii=False)
        budget_analysis_json = json.dumps(budget_analysis, indent=2, ensure_ascii=False)
        # Convertir les booléens Python en minuscules pour JSON standard dans la liste
        docs_analyses_std_bool = [{k: (str(v).lower() if isinstance(v, bool) else v) for k, v in doc.items()} for doc in documents_analyses]
        documents_analysis_json = json.dumps(docs_analyses_std_bool, indent=2, ensure_ascii=False)
    except Exception as json_err:
        print(f"ERREUR: Impossible de convertir les données d'entrée en JSON pour le prompt: {json_err}")
        return None

    # Construire le prompt final
    final_prompt = PROMPT_MESSAGE_OVERALL_ASSESSMENT.format(
        form_data_json=form_data_json,
        budget_analysis_json=budget_analysis_json,
        documents_analysis_json=documents_analysis_json,
        json_format=JSON_FORMAT_OVERALL_ASSESSMENT
    )

    # Appeler l'API OpenAI avec GPT-4.1
    model_to_use = "gpt-4-0125-preview" # Utiliser un alias spécifique de gpt-4 / gpt-4.1 si disponible, sinon gpt-4
    # Mettez ici l'identifiant exact du modèle gpt-4.1 que vous voulez utiliser si vous en avez un spécifique
    # exemple: model_to_use = "gpt-4.1-xxxx-xx-xx"
    print(f"Utilisation du modèle: {model_to_use}")

    try:
        print("Envoi de la requête d'évaluation globale à l'API OpenAI...")
        response = client.chat.completions.create(
            model=model_to_use,
            messages=[
                {"role": "system", "content": PROMPT_INSTRUCTIONS_OVERALL_ASSESSMENT},
                {"role": "user", "content": final_prompt}
            ],
            # max_tokens=1500, # Donner plus de tokens pour la synthèse
            temperature=0.3, # Un peu plus de créativité pour la synthèse mais rester factuel
            response_format={ "type": "json_object" }
        )

        json_response_str = response.choices[0].message.content
        print("Réponse d'évaluation globale reçue d'OpenAI.")

        # Parser la réponse JSON
        try:
            assessment_json = json.loads(json_response_str)
            print("Réponse JSON d'évaluation globale parsée avec succès.")
            return assessment_json
        except json.JSONDecodeError as json_error:
            print(f"ERREUR: Impossible de parser la réponse JSON d'évaluation globale: {json_error}")
            print(f"Réponse reçue: {json_response_str}")
            return {
                "status": "ERROR_PARSING_RESPONSE",
                "summary_of_findings": "La réponse du LLM pour l'évaluation globale n'était pas un JSON valide.",
                "missing_elements_or_clarifications": ["Vérifier la réponse brute du LLM."],
                "final_recommendation": "Évaluation échouée.",
                "suggested_email_template": "error",
                "raw_response": json_response_str
            }

    except Exception as e:
        print(f"ERREUR lors de l'appel API pour l'évaluation globale: {e}")
        traceback.print_exc()
        return None

# --- Fonction de Génération d'Email HTML Demandeur ---
def generate_applicant_html_email(assessment_data: dict, applicant_data: dict, budget_analysis_data: dict, supporting_docs_data: list):
    """Génère le corps HTML de l'email pour le DEMANDEUR.
       Se concentre sur le statut, les actions requises et un résumé simplifié.
    """
    if not client:
        print("ERREUR: Client OpenAI non initialisé.")
        return None

    print("\n--- Génération de l'email HTML pour le demandeur (Texte Header) ---")
    try:
        assessment_data_json = json.dumps(assessment_data, indent=2, ensure_ascii=False)
        budget_analysis_json = json.dumps(budget_analysis_data, indent=2, ensure_ascii=False)
        docs_data_std_bool = [{k: (str(v).lower() if isinstance(v, bool) else v) for k, v in doc.items()} for doc in supporting_docs_data]
        supporting_docs_json = json.dumps(docs_data_std_bool, indent=2, ensure_ascii=False)
    except Exception as json_err:
        print(f"ERREUR JSON (Applicant Email): {json_err}")
        return None

    final_prompt = PROMPT_MESSAGE_APPLICANT_HTML_EMAIL.format(
        responsible_name=applicant_data.get('responsible_name', '[Nom Manquant]'),
        project_name=applicant_data.get('project_name', '[Projet Manquant]'),
        assessment_data_json=assessment_data_json,
        budget_analysis_json=budget_analysis_json,
        supporting_docs_json=supporting_docs_json,
        remaining_amount=applicant_data.get('remaining_amount', '[Montant Manquant]')
    )
    model_to_use = "gpt-4-0125-preview"
    try:
        response = client.chat.completions.create(
            model=model_to_use,
            messages=[
                {"role": "system", "content": PROMPT_INSTRUCTIONS_APPLICANT_HTML_EMAIL},
                {"role": "user", "content": final_prompt}
            ],
            max_tokens=3500, temperature=0.4
        )
        html_content = response.choices[0].message.content
        
        # NETTOYAGE AMÉLIORÉ du HTML pour enlever toutes les balises Markdown
        # Supprimer complètement les balises Markdown ```html ou ``` au début
        if html_content.strip().startswith("```html"):
            html_content = html_content.strip()[7:].strip()
        elif html_content.strip().startswith("```"):
            html_content = html_content.strip()[3:].strip()
            
        # Enlever les ``` de la fin si présents
        if html_content.strip().endswith("```"):
            html_content = html_content.strip()[:-3].strip()
            
        # Vérification supplémentaire pour éliminer d'autres balises Markdown potentielles
        # Cela inclut les cas où le modèle pourrait ajouter des balises comme ```html au milieu du contenu
        html_content = html_content.replace("```html", "").replace("```", "")
        
        # Vérifier si le contenu commence par <!DOCTYPE html>
        if not html_content.strip().lower().startswith("<!doctype html"):
            print("WARN: La réponse pour l'email demandeur ne commence pas par <!DOCTYPE html>. Wrapper ajouté.")
            html_content = f"<!DOCTYPE html><html><head><meta charset=\"UTF-8\"></head><body>{html_content}</body></html>"
            
        print("Corps HTML de l'email demandeur généré et nettoyé avec succès.")
        return html_content
    except Exception as e:
        print(f"ERREUR API (Applicant Email): {e}")
        traceback.print_exc()
        return None

# --- Fonction de Génération d'Email HTML INTERNE --- 
def generate_internal_review_email(assessment_data: dict, applicant_data: dict, budget_analysis_data: dict, supporting_docs_data: list, validator_name: str):
    """Génère le corps HTML de l'email pour le VALIDEUR.
       Inclut tous les détails de l'analyse pour une prise de décision éclairée.
    """
    if not client:
        print("ERREUR: Client OpenAI non initialisé.")
        return None

    print("\n--- Génération de l'email HTML pour le valideur (Texte Header) ---")
    try:
        assessment_data_json = json.dumps(assessment_data, indent=2, ensure_ascii=False)
        budget_analysis_json = json.dumps(budget_analysis_data, indent=2, ensure_ascii=False)
        docs_data_std_bool = [{k: (str(v).lower() if isinstance(v, bool) else v) for k, v in doc.items()} for doc in supporting_docs_data]
        supporting_docs_json = json.dumps(docs_data_std_bool, indent=2, ensure_ascii=False)
    except Exception as json_err:
        print(f"ERREUR JSON (Internal Email): {json_err}")
        return None

    final_prompt = PROMPT_MESSAGE_INTERNAL_HTML_EMAIL.format(
        validator_name=validator_name,
        responsible_name=applicant_data.get('responsible_name', '[Nom Manquant]'),
        project_name=applicant_data.get('project_name', '[Projet Manquant]'),
        assessment_data_json=assessment_data_json,
        budget_analysis_json=budget_analysis_json,
        supporting_docs_json=supporting_docs_json,
        remaining_amount=applicant_data.get('remaining_amount', '[Montant Manquant]')
    )
    model_to_use = "gpt-4-0125-preview"
    try:
        response = client.chat.completions.create(
            model=model_to_use,
            messages=[
                {"role": "system", "content": PROMPT_INSTRUCTIONS_INTERNAL_HTML_EMAIL},
                {"role": "user", "content": final_prompt}
            ],
            max_tokens=4000, temperature=0.4
        )
        html_content = response.choices[0].message.content
        
        # NETTOYAGE AMÉLIORÉ du HTML pour enlever toutes les balises Markdown
        # Supprimer complètement les balises Markdown ```html ou ``` au début
        if html_content.strip().startswith("```html"):
            html_content = html_content.strip()[7:].strip()
        elif html_content.strip().startswith("```"):
            html_content = html_content.strip()[3:].strip()
            
        # Enlever les ``` de la fin si présents
        if html_content.strip().endswith("```"):
            html_content = html_content.strip()[:-3].strip()
            
        # Vérifier si le contenu commence par <!DOCTYPE html>
        if not html_content.strip().lower().startswith("<!doctype html"):
            print("WARN: La réponse pour l'email valideur ne commence pas par <!DOCTYPE html>. Wrapper ajouté.")
            html_content = f"<!DOCTYPE html><html><head><meta charset=\"UTF-8\"></head><body>{html_content}</body></html>"
            
        print("Corps HTML de l'email valideur généré et nettoyé avec succès.")
        return html_content
    except Exception as e:
        print(f"ERREUR API (Internal Email): {e}")
        traceback.print_exc()
        return None

# --- Exemple d'utilisation (mis à jour pour montrer l'option PDF) ---
if __name__ == '__main__':
    # Créer un fichier texte et une image factice pour le test
    test_text_file = "supporting_doc_test.txt"
    test_image_file = "supporting_doc_test.png" # Nécessite Pillow installé: pip install Pillow
    # Vous pouvez remplacer test_image_file par le chemin d'une vraie image si Pillow n'est pas installé
    # test_image_file = "path/to/your/test_image.jpg" 

    with open(test_text_file, "w") as f:
        f.write("Facture F001\nFournisseur: ACME Corp\nDate: 15/03/2025\nMontant: 150.00 EUR\nDescription: Achat matériel bureau")
    print(f"Fichier texte de test créé: {test_text_file}")
    
    try:
        from PIL import Image, ImageDraw
        img = Image.new('RGB', (200, 100), color = (73, 109, 137))
        d = ImageDraw.Draw(img)
        d.text((10,10), "Test Image 2025", fill=(255,255,0))
        img.save(test_image_file)
        print(f"Image de test créée: {test_image_file}")
        image_test_possible = True
    except ImportError:
        print("WARN: Module Pillow (PIL) non trouvé. Le test d'image sera sauté.")
        print("      Pour tester l'image, installez Pillow: pip install Pillow")
        print(f"      Ou modifiez la variable 'test_image_file' pour pointer vers une image existante.")
        image_test_possible = False
    except Exception as img_err:
        print(f"Erreur lors de la création de l'image de test: {img_err}")
        image_test_possible = False
        # Assurez-vous que le chemin est valide si vous ne créez pas l'image
        if not os.path.exists(test_image_file):
             test_image_file = None # Ne pas tenter d'analyser si le fichier n'existe pas
        else:
             image_test_possible = True # Si l'image existe déjà

    # Créer un fichier PDF factice pour le test (si reportlab est dispo)
    test_pdf_file = "supporting_doc_test.pdf"
    pdf_test_possible = False
    reportlab_installed = False
    try:
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import letter
        reportlab_installed = True
    except ImportError:
         print("WARN: Module reportlab non trouvé. La création automatique de PDF de test est désactivée.")
         print("      Pour tester le PDF, assurez-vous qu'un fichier nommé 'supporting_doc_test.pdf' existe")
         print("      ou installez reportlab: pip install reportlab")
         # Vérifier si un fichier existe déjà
         if os.path.exists(test_pdf_file):
              print(f"INFO: Utilisation du fichier PDF existant: {test_pdf_file}")
              pdf_test_possible = True
         else:
              test_pdf_file = None # Ne pas tester si pas de reportlab et pas de fichier
              
    if reportlab_installed:
        try:
            c = canvas.Canvas(test_pdf_file, pagesize=letter)
            c.drawString(100, 750, "Facture PDF F002 - Test")
            c.drawString(100, 735, "Fournisseur: PDFGen Services")
            c.drawString(100, 720, "Date: 2025-04-01")
            c.drawString(100, 705, "Montant: 99.99 EUR")
            c.save()
            print(f"Fichier PDF de test créé: {test_pdf_file}")
            pdf_test_possible = True
        except Exception as pdf_err:
            print(f"Erreur lors de la création du PDF de test avec reportlab: {pdf_err}")
            if os.path.exists(test_pdf_file):
                 print(f"INFO: Utilisation du fichier PDF existant malgré l'erreur: {test_pdf_file}")
                 pdf_test_possible = True
            else:
                 test_pdf_file = None
                 
    dummy_project_context = {
        'project_name': "Projet Alpha",
        'project_description': "Développement d'une nouvelle plateforme.",
        'expense_categories': "IT Equipment, Personnel Costs"
    }

    # Tester l'analyse du fichier texte
    print("\n--- Test Analyse Document Texte ---")
    text_analysis_result = analyse_supporting_document(test_text_file, dummy_project_context)
    if text_analysis_result:
        print("Résultat Analyse Texte (JSON):")
        print(json.dumps(text_analysis_result, indent=2))
    else:
        print("Échec de l'analyse du document texte.")

    # Tester l'analyse de l'image (si possible/existante)
    if image_test_possible and test_image_file:
        print("\n--- Test Analyse Document Image ---")
        image_analysis_result = analyse_supporting_document(test_image_file, dummy_project_context)
        if image_analysis_result:
            print("Résultat Analyse Image (JSON):")
            print(json.dumps(image_analysis_result, indent=2))
        else:
            print("Échec de l'analyse du document image.")
    elif test_image_file:
         print(f"\nSkipping image analysis test for {test_image_file}.")
    else:
         print("\nSkipping image analysis test as no valid image path provided.")

    pdf_analysis_direct = None
    pdf_analysis_image = None

    # Tester l'analyse PDF (méthode directe)
    if pdf_test_possible and test_pdf_file:
        print("\n--- Test Analyse Document PDF (Méthode Directe) ---")
        pdf_analysis_direct = analyse_supporting_document(test_pdf_file, dummy_project_context, pdf_handling_method='direct')
        if pdf_analysis_direct:
            print("Résultat Analyse PDF Directe (JSON):")
            print(json.dumps(pdf_analysis_direct, indent=2))
        else:
            print("Échec de l'analyse PDF (méthode directe).")

        # Tester l'analyse PDF (méthode conversion image)
        if pdf2image_installed:
            print("\n--- Test Analyse Document PDF (Méthode Conversion Image) ---")
            pdf_analysis_image = analyse_supporting_document(test_pdf_file, dummy_project_context, pdf_handling_method='image')
            if pdf_analysis_image:
                print("Résultat Analyse PDF via Image (JSON):")
                print(json.dumps(pdf_analysis_image, indent=2))
            else:
                print("Échec de l'analyse PDF (méthode conversion image). Vérifiez si Poppler est installé.")
        else:
             print("\nSkipping PDF via image test: pdf2image non installé.")
    else:
        print("\nSkipping PDF analysis tests: Aucun fichier PDF de test valide.")

    # --- Test Évaluation Globale (mise à jour pour inclure les résultats PDF) --- 
    print("\n--- Test Évaluation Globale du Dossier (avec résultats PDF potentiels) ---")
    # Simuler les données d'entrée pour l'évaluation globale
    simulated_form_data = {
        'project_name': "Projet Alpha",
        'total_allocated': 5000,
        'amount_spent': 150, # Mettre une valeur différente pour tester détection incohérence
        'amount_already_paid': 50,
        'remaining_amount': 100,
        # Ajouter d'autres champs pertinents du formulaire...
    }
    # Simuler une analyse Excel (on prendrait le retour de analysis.py normalement)
    simulated_budget_analysis = {
        "excel_total_budget": 5000,
        "excel_total_spent": 150.00, # Correspond au texte mais pas au form
        "excel_already_paid": 50,
        "excel_remaining": 100,
        "budget_period": "2025",
        "matches_form_data": False, # Simuler une incohérence détectée par Python
        "discrepancies": [{
             "field": "Total Amount Spent",
             "form_value": 150, 
             "excel_value": 150.00,
             "issue": "Valeur différente du formulaire (simulé)."
        }],
        "expense_categories_analysis": [],
        "dates_in_2025": True,
        "detailed_expenses_total_matches": True,
        "completeness": "complete",
        "quality_assessment": "high",
        "issues_identified": ["Incohérence simulée avec formulaire"],
        "overall_conclusion": "Analyse Python OK mais incohérence form/Excel."
    }
    # Combiner les analyses des pièces justificatives (si elles existent)
    simulated_docs_analyses = []
    if text_analysis_result:
        simulated_docs_analyses.append(text_analysis_result)
    if image_analysis_result:
         simulated_docs_analyses.append(image_analysis_result)
    if pdf_analysis_direct:
         simulated_docs_analyses.append(pdf_analysis_direct)
    if not simulated_docs_analyses: # Ajouter une analyse factice si aucune n'a réussi
         simulated_docs_analyses.append({"document_type": "Factice", "conclusion": "Aucun document réel analysé pour ce test."}) 

    # Appeler la fonction d'évaluation globale
    overall_assessment_result = assess_overall_dossier(
        simulated_form_data,
        simulated_budget_analysis,
        simulated_docs_analyses
    )

    if overall_assessment_result:
        print("\nRésultat Évaluation Globale (JSON):")
        print(json.dumps(overall_assessment_result, indent=2, ensure_ascii=False))
        
        # --- Test Génération Email HTML Enrichi --- 
        print("\n--- Test Génération Email HTML Détaillé (Enrichi) ---")
        applicant_data_for_email = {
             'responsible_name': simulated_form_data.get('responsible_name', 'Cher Contact'),
             'project_name': simulated_form_data.get('project_name', '[Nom Projet]'),
             'responsible_email': 'test@example.com', # Non utilisé pour la génération, juste pour contexte
             'remaining_amount': simulated_form_data.get('remaining_amount')
        }
        
        generated_html_applicant = generate_applicant_html_email(
            assessment_data=overall_assessment_result,
            applicant_data=applicant_data_for_email,
            budget_analysis_data=simulated_budget_analysis,
            supporting_docs_data=simulated_docs_analyses
        )
        
        if generated_html_applicant:
            print("\nHTML généré (début):")
            print(generated_html_applicant[:1000] + "...")
            # Sauvegarder l'HTML dans un fichier pour inspection facile
            try:
                with open("generated_email_preview.html", "w", encoding="utf-8") as f_html:
                    f_html.write(generated_html_applicant)
                print("\nEmail HTML complet sauvegardé dans: generated_email_preview.html")
            except Exception as write_err:
                print(f"WARN: Impossible de sauvegarder l'aperçu HTML: {write_err}")
        else:
            print("\nÉchec de la génération de l'email HTML.")
            
        # --- Test Génération Email HTML Interne --- 
        print("\n--- Test Génération Email HTML Interne ---")
        # Utiliser les mêmes données globales pour le test
        generated_html_internal = generate_internal_review_email(
             assessment_data=overall_assessment_result,
             applicant_data=applicant_data_for_email, # Contient nom, projet
             budget_analysis_data=simulated_budget_analysis,
             supporting_docs_data=simulated_docs_analyses,
             validator_name="Équipe de la Fondation ESCP"
         )
        if generated_html_internal:
            print("\nHTML interne généré (début):")
            print(generated_html_internal[:1000] + "...")
            # Sauvegarder l'HTML interne dans un fichier
            try:
                with open("internal_email_preview.html", "w", encoding="utf-8") as f_html_int:
                    f_html_int.write(generated_html_internal)
                print("\nEmail HTML interne complet sauvegardé dans: internal_email_preview.html")
            except Exception as write_err:
                print(f"WARN: Impossible de sauvegarder l'aperçu HTML interne: {write_err}")
        else:
            print("\nÉchec de la génération de l'email HTML interne.")
            
    else:
        print("\nÉchec de l'évaluation globale du dossier (pas de test HTML possible).")

    # --- Nettoyage ---
    # import os
    # if os.path.exists(test_text_file): os.remove(test_text_file)
    # if image_test_possible and os.path.exists(test_image_file): os.remove(test_image_file) 
    if pdf_test_possible and test_pdf_file and os.path.exists(test_pdf_file): 
         try: os.remove(test_pdf_file)
         except OSError: pass 