import os
import traceback
from typing import Union, Tuple

TEMPLATE_DIR = "templates"


def load_template(template_name: str) -> Union[str, None]:
    """Charge le contenu d'un fichier template."""
    file_path = os.path.join(TEMPLATE_DIR, template_name)
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        print(f"ERREUR: Template email introuvable: {file_path}")
        return None
    except Exception as e:
        print(f"ERREUR lors de la lecture du template {file_path}: {e}")
        traceback.print_exc()
        return None


def format_missing_elements(missing_list: list) -> str:
    """Met en forme la liste des éléments manquants pour l'email."""
    if not missing_list:
        return "- Aucun problème spécifique identifié (vérification manuelle recommandée)."
    
    # Créer une liste à puces
    formatted = "\n".join([f"- {item}" for item in missing_list])
    return formatted

def prepare_email_content(template_key: str, data: dict) -> Tuple[Union[str, None], Union[str, None]]:
    """Prépare le sujet et le corps HTML d'un email basé sur un template et des données.

    Args:
        template_key: 'approval', 'additional_info', ou 'incomplete'.
        data: Dictionnaire contenant les données pour remplir le template,
              ex: {
                  'responsible_name': "M. Dupont",
                  'project_name': "Projet Alpha",
                  'remaining_amount': 2550,
                  'missing_elements_or_clarifications': ["Facture XYZ manquante", "Clarifier dépense ABC"]
              }

    Returns:
        tuple: (sujet, corps_html) ou (None, None) en cas d'erreur.
    """
    template_filename = f"{template_key}_email.txt"
    raw_content = load_template(template_filename)

    if not raw_content:
        return None, None

    try:
        # Séparer le sujet du corps (première ligne "Subject: ...")
        lines = raw_content.split('\n', 1)
        subject_line = lines[0]
        body_template = lines[1].strip() if len(lines) > 1 else ""

        if subject_line.lower().startswith("subject:"):
            subject = subject_line[len("subject:"):].strip()
        else:
            print(f"WARN: Pas de ligne 'Subject:' trouvée dans {template_filename}. Utilisation d'un sujet par défaut.")
            subject = f"Mise à jour concernant votre projet {data.get('project_name', '')}"
            body_template = raw_content # Utiliser tout le contenu si pas de ligne Subject
        
        # Préparer les données pour le formatage
        format_data = data.copy()
        format_data['missing_elements_list'] = format_missing_elements(
            data.get('missing_elements_or_clarifications', [])
        )
        # S'assurer que les clés nécessaires existent (même si vides)
        format_data.setdefault('responsible_name', "[Nom Responsable Manquant]")
        format_data.setdefault('project_name', "[Nom Projet Manquant]")
        format_data.setdefault('remaining_amount', "[Montant Manquant]")

        # Remplacer les placeholders (gestion simple avec f-string ou .format)
        # Pour une gestion plus robuste, on pourrait utiliser Jinja2
        # Ici, on utilise .format après avoir préparé les clés
        final_subject = subject.format(**format_data)
        final_body = body_template.format(**format_data)
        
        # Convertir le corps en HTML simple (remplacer les sauts de ligne par <br>)
        # Pour un HTML plus riche, on pourrait utiliser des templates HTML dédiés
        final_body_html = final_body.replace("\n", "<br>")

        print(f"Contenu email préparé pour le template: {template_key}")
        return final_subject, final_body_html

    except KeyError as e:
        print(f"ERREUR: Placeholder manquant dans les données ou le template {template_filename}: {e}")
        traceback.print_exc()
        return None, None
    except Exception as e:
        print(f"ERREUR lors du formatage de l'email ({template_filename}): {e}")
        traceback.print_exc()
        return None, None

# --- Exemple d'utilisation --- 
if __name__ == '__main__':
    print("--- Test Préparation Email Approbation ---")
    approval_data = {
        'responsible_name': "Mme Martin",
        'project_name': "Projet Beta",
        'remaining_amount': 1234.56
    }
    subject, body = prepare_email_content('approval', approval_data)
    if subject and body:
        print(f"Sujet: {subject}")
        body_for_print = body.replace('<br>','\n')
        print(f"Corps:\n{body_for_print[:300]}...") # Afficher début corps
    else:
        print("Échec préparation email approbation.")

    print("\n--- Test Préparation Email Infos Complémentaires ---")
    info_data = {
        'responsible_name': "M. Durand",
        'project_name': "Projet Gamma",
        'missing_elements_or_clarifications': [
            "Facture pour l'achat de l'équipement X.",
            "Préciser la nature des frais de déplacement du 15/03."
        ]
    }
    subject, body = prepare_email_content('additional_info', info_data)
    if subject and body:
        print(f"Sujet: {subject}")
        body_for_print = body.replace('<br>','\n')
        print(f"Corps:\n{body_for_print[:400]}...")
    else:
        print("Échec préparation email infos complémentaires.")

    print("\n--- Test Préparation Email Incomplet ---")
    incomplete_data = {
        'responsible_name': "Mlle Petit",
        'project_name': "Projet Delta",
        'missing_elements_or_clarifications': [
            "Fichier budget Excel non conforme (onglet manquant).",
            "Aucune pièce justificative fournie pour la catégorie Personnel Costs.",
            "Dates hors période 2025 détectées."
        ]
    }
    subject, body = prepare_email_content('incomplete', incomplete_data)
    if subject and body:
        print(f"Sujet: {subject}")
        body_for_print = body.replace('<br>','\n')
        print(f"Corps:\n{body_for_print[:400]}...")
    else:
        print("Échec préparation email incomplet.") 