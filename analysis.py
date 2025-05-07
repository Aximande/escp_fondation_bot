import pandas as pd
from datetime import datetime
import numpy as np
import traceback

def analyse_budget_excel(excel_path: str, form_data: dict):
    """Analyse le fichier Excel budgétaire standardisé.

    Args:
        excel_path: Chemin vers le fichier Excel.
        form_data: Dictionnaire contenant les données déclarées dans le formulaire,
                   ex: {
                       'total_allocated': 10000,
                       'amount_spent': 8000,
                       'amount_already_paid': 5000,
                       'remaining_amount': 3000
                   }

    Returns:
        dict: Un dictionnaire contenant les résultats de l'analyse,
              structuré selon le format JSON attendu.
    """
    print(f"\n--- Début de l'analyse du fichier budget: {excel_path} ---")
    analysis_result = {
        "excel_total_budget": None,
        "excel_total_spent": None,
        "excel_already_paid": None,
        "excel_remaining": None,
        "budget_period": None,
        "matches_form_data": True, # Sera mis à False si une incohérence est trouvée
        "discrepancies": [],
        "expense_categories_analysis": [],
        "dates_in_2025": True, # Sera mis à False si une date est hors 2025
        "detailed_expenses_total_matches": True, # Sera mis à False si incohérent
        "completeness": "incomplete", # Sera mis à jour (complete, partial, incomplete)
        "quality_assessment": "low", # Sera mis à jour (high, medium, low)
        "issues_identified": [],
        "overall_conclusion": ""
    }

    expected_sheets = ["Budget Summary", "Expense Categories", "Detailed Expenses"]
    found_sheets = []
    all_sheets_present = False

    try:
        xls = pd.ExcelFile(excel_path)
        found_sheets = xls.sheet_names
        print(f"Onglets trouvés: {found_sheets}")

        missing_sheets = [sheet for sheet in expected_sheets if sheet not in found_sheets]
        if not missing_sheets:
            all_sheets_present = True
            analysis_result["completeness"] = "partial" # Au moins les onglets sont là
            print("Tous les onglets requis sont présents.")
        else:
            issue = f"Onglet(s) manquant(s): {', '.join(missing_sheets)}"
            analysis_result["issues_identified"].append(issue)
            print(f"ERREUR: {issue}")
            analysis_result["overall_conclusion"] = "Fichier incomplet (onglets manquants)."
            return analysis_result # Arrêter l'analyse si les onglets manquent

        # --- 1. Analyse Onglet "Budget Summary" --- 
        print("\nAnalyse de l'onglet 'Budget Summary'...")
        try:
            # header=None car pas d'en-tête standard, index_col=0 pour utiliser la colonne 'Field'
            df_summary = pd.read_excel(xls, sheet_name="Budget Summary", header=None, index_col=0, names=['Field', 'Value'])
            df_summary.index = df_summary.index.str.strip() # Nettoyer les espaces
            df_summary['Value'] = df_summary['Value'].apply(lambda x: pd.to_numeric(x, errors='coerce') if isinstance(x, (int, float)) else x)
            df_summary['Value'] = df_summary['Value'].fillna(0) # Remplacer NaN par 0 pour les calculs
            # print(df_summary)

            # Extraire les valeurs spécifiques
            summary_data = {}
            expected_fields = [
                "Project Name", "Campus", "EOTP Code", "Total Budget Allocated",
                "Total Amount Spent", "Amount Already Paid", "Remaining Amount to Pay",
                "Budget Period"
            ]
            for field in expected_fields:
                if field in df_summary.index:
                    summary_data[field] = df_summary.loc[field, 'Value']
                else:
                    summary_data[field] = None
                    issue = f"Champ manquant dans 'Budget Summary': {field}"
                    analysis_result["issues_identified"].append(issue)
                    print(f"WARN: {issue}")
                    analysis_result["completeness"] = "incomplete"

            # Stocker les valeurs extraites
            analysis_result["excel_total_budget"] = summary_data.get("Total Budget Allocated", 0)
            analysis_result["excel_total_spent"] = summary_data.get("Total Amount Spent", 0)
            analysis_result["excel_already_paid"] = summary_data.get("Amount Already Paid", 0)
            analysis_result["excel_remaining"] = summary_data.get("Remaining Amount to Pay", 0)
            analysis_result["budget_period"] = summary_data.get("Budget Period")

            print(f"  Total Budget (Excel): {analysis_result['excel_total_budget']}")
            print(f"  Total Spent (Excel): {analysis_result['excel_total_spent']}")
            print(f"  Already Paid (Excel): {analysis_result['excel_already_paid']}")
            print(f"  Remaining (Excel): {analysis_result['excel_remaining']}")
            print(f"  Budget Period (Excel): {analysis_result['budget_period']}")

            # Vérification de la période budgétaire (doit être 2025)
            if analysis_result["budget_period"]:
                # Simple vérification si '2025' est dans la chaîne (peut être affinée)
                if "2025" not in str(analysis_result["budget_period"]):
                    issue = f"La période budgétaire dans 'Budget Summary' ('{analysis_result['budget_period']}') ne contient pas '2025'."
                    analysis_result["issues_identified"].append(issue)
                    print(f"WARN: {issue}")
            else:
                 issue = f"La période budgétaire ('Budget Period') est manquante dans 'Budget Summary'."
                 analysis_result["issues_identified"].append(issue)
                 print(f"WARN: {issue}")

            # Comparaison avec les données du formulaire
            form_comparisons = {
                "Total Budget Allocated": form_data.get('total_allocated'),
                "Total Amount Spent": form_data.get('amount_spent'),
                "Amount Already Paid": form_data.get('amount_already_paid'),
                "Remaining Amount to Pay": form_data.get('remaining_amount')
            }

            for field, form_value in form_comparisons.items():
                excel_value = summary_data.get(field)
                if excel_value is not None and form_value is not None:
                    try:
                        # Convertir en nombres pour comparaison fiable
                        numeric_excel_value = pd.to_numeric(excel_value, errors='raise')
                        numeric_form_value = pd.to_numeric(form_value, errors='raise')
                        # Utiliser une tolérance pour les comparaisons de floats
                        if not np.isclose(numeric_excel_value, numeric_form_value, rtol=1e-5):
                            discrepancy = {
                                "field": field,
                                "form_value": numeric_form_value,
                                "excel_value": numeric_excel_value,
                                "issue": "Différence entre la valeur du formulaire et celle de l'Excel."
                            }
                            analysis_result["discrepancies"].append(discrepancy)
                            analysis_result["matches_form_data"] = False
                            print(f"DISCREPANCY: {field} - Form: {numeric_form_value}, Excel: {numeric_excel_value}")
                    except (ValueError, TypeError) as conv_error:
                         issue = f"Impossible de comparer numériquement le champ '{field}'. Form: '{form_value}', Excel: '{excel_value}'. Erreur: {conv_error}"
                         analysis_result["issues_identified"].append(issue)
                         print(f"WARN: {issue}")
                         analysis_result["matches_form_data"] = False # Marquer comme incohérent
                elif excel_value is None:
                     print(f"WARN: Champ '{field}' manquant dans Excel pour comparaison.")
                # Ne pas signaler si la valeur form est None, car elle peut être optionnelle

            if analysis_result["matches_form_data"]:
                 print("OK: Les valeurs de 'Budget Summary' correspondent aux données du formulaire.")
            else:
                 print("ERREUR: Incohérences trouvées entre 'Budget Summary' et les données du formulaire.")
                 analysis_result["issues_identified"].append("Incohérences trouvées entre 'Budget Summary' et les données du formulaire.")

            # Vérification du calcul Remaining Amount to Pay
            if analysis_result["excel_total_spent"] is not None and analysis_result["excel_already_paid"] is not None and analysis_result["excel_remaining"] is not None:
                calculated_remaining = analysis_result["excel_total_spent"] - analysis_result["excel_already_paid"]
                if not np.isclose(analysis_result["excel_remaining"], calculated_remaining, rtol=1e-5):
                    issue = f"Calcul incorrect du 'Remaining Amount to Pay' dans 'Budget Summary'. Attendu: {calculated_remaining}, Trouvé: {analysis_result['excel_remaining']}"
                    analysis_result["issues_identified"].append(issue)
                    print(f"ERREUR: {issue}")
                else:
                     print("OK: Calcul 'Remaining Amount to Pay' cohérent.")
            else:
                 print("WARN: Impossible de vérifier le calcul 'Remaining Amount to Pay' (valeurs manquantes).")


        except Exception as e:
            issue = f"Erreur lors de l'analyse de l'onglet 'Budget Summary': {e}"
            analysis_result["issues_identified"].append(issue)
            print(f"ERREUR: {issue}")
            traceback.print_exc()
            analysis_result["completeness"] = "incomplete"

        # --- 2. Analyse Onglet "Expense Categories" --- 
        print("\nAnalyse de l'onglet 'Expense Categories'...")
        total_categories_spent = None
        try:
            # skiprows=0 pour utiliser la première ligne comme en-tête
            df_categories = pd.read_excel(xls, sheet_name="Expense Categories", skiprows=0)
            df_categories = df_categories.dropna(how='all') # Supprimer lignes vides
            # Renommer colonnes pour accès facile (supposer l'ordre standard)
            expected_cols = ["Expense Category", "Allocated Budget", "Actual Expenses", "Variance", "% Executed"]
            if len(df_categories.columns) >= len(expected_cols):
                 df_categories.columns = expected_cols + list(df_categories.columns[len(expected_cols):])
                 # Convertir les colonnes numériques, mettre 0 si erreur
                 for col in ["Allocated Budget", "Actual Expenses", "Variance"]: # % Executed peut être texte
                      df_categories[col] = pd.to_numeric(df_categories[col], errors='coerce').fillna(0)
                 # print(df_categories)

                 # Extraire les données par catégorie et vérifier les écarts
                 for index, row in df_categories.iterrows():
                    category_name = row["Expense Category"]
                    # Ignorer la ligne TOTAL si présente
                    if isinstance(category_name, str) and "TOTAL" in category_name.upper():
                        total_categories_spent = row["Actual Expenses"]
                        print(f"  Total trouvé dans 'Expense Categories': {total_categories_spent}")
                        continue # Passer à la ligne suivante
                    
                    allocated = row["Allocated Budget"]
                    spent = row["Actual Expenses"]
                    variance = row["Variance"] # On prend la valeur Excel pour l'instant
                    # variance_percent = row["% Executed"]

                    significant_variance = False
                    variance_percent_calc = 0
                    if allocated > 0:
                        variance_percent_calc = (spent / allocated) * 100
                        # Ecart significatif si > 5% de différence par rapport au budgeté
                        if abs(spent - allocated) / allocated > 0.05:
                            significant_variance = True
                    elif spent > 0: # Dépense sans budget alloué -> écart significatif
                         significant_variance = True
                         variance_percent_calc = float('inf') # Dépense sur budget zéro
                    
                    category_analysis = {
                        "category": category_name,
                        "allocated": allocated,
                        "spent": spent,
                        "variance": variance, # Garder celui de l'Excel pour l'instant
                        "variance_percent": f"{variance_percent_calc:.2f}%" if variance_percent_calc != float('inf') else "N/A (Budget 0)",
                        "significant_variance": significant_variance
                    }
                    analysis_result["expense_categories_analysis"].append(category_analysis)

                    if significant_variance:
                         issue = f"Écart significatif (>5%) détecté pour la catégorie '{category_name}'. Alloué: {allocated}, Dépensé: {spent}"
                         analysis_result["issues_identified"].append(issue)
                         print(f"WARN: {issue}")
                 
                 # Comparer le total des catégories avec le total dépensé du Summary
                 if total_categories_spent is not None and analysis_result["excel_total_spent"] is not None:
                    if not np.isclose(total_categories_spent, analysis_result["excel_total_spent"], rtol=1e-5):
                         issue = f"Incohérence entre le total dépensé de 'Budget Summary' ({analysis_result['excel_total_spent']}) et le TOTAL de 'Expense Categories' ({total_categories_spent})."
                         analysis_result["issues_identified"].append(issue)
                         print(f"ERREUR: {issue}")
                    else:
                        print("OK: Total 'Expense Categories' cohérent avec 'Budget Summary'.")
                 else:
                    issue="Impossible de comparer le total des catégories (TOTAL manquant ou total Budget Summary manquant)."
                    analysis_result["issues_identified"].append(issue)
                    print(f"WARN: {issue}")

            else:
                 issue = f"Nombre de colonnes insuffisant dans l'onglet 'Expense Categories'. Attendu: {len(expected_cols)}, Trouvé: {len(df_categories.columns)}"
                 analysis_result["issues_identified"].append(issue)
                 print(f"ERREUR: {issue}")
                 analysis_result["completeness"] = "incomplete"

        except Exception as e:
            issue = f"Erreur lors de l'analyse de l'onglet 'Expense Categories': {e}"
            analysis_result["issues_identified"].append(issue)
            print(f"ERREUR: {issue}")
            traceback.print_exc()
            analysis_result["completeness"] = "incomplete"

        # --- 3. Analyse Onglet "Detailed Expenses" --- 
        print("\nAnalyse de l'onglet 'Detailed Expenses'...")
        total_detailed_spent = 0
        try:
            df_detailed = pd.read_excel(xls, sheet_name="Detailed Expenses", skiprows=0)
            df_detailed = df_detailed.dropna(how='all')
            expected_cols_detail = ["Date", "Expense Category", "Description", "Supplier", "Amount", "Invoice Reference"]
            if len(df_detailed.columns) >= len(expected_cols_detail):
                df_detailed.columns = expected_cols_detail + list(df_detailed.columns[len(expected_cols_detail):])
                # Convertir Amount en numérique
                df_detailed["Amount"] = pd.to_numeric(df_detailed["Amount"], errors='coerce').fillna(0)
                total_detailed_spent = df_detailed["Amount"].sum()
                print(f"  Total calculé depuis 'Detailed Expenses': {total_detailed_spent}")

                # Convertir les dates et vérifier si elles sont en 2025
                all_dates_ok = True
                for index, row in df_detailed.iterrows():
                    date_val = row["Date"]
                    try:
                        # Essayer de convertir la date (gère différents formats)
                        parsed_date = pd.to_datetime(date_val)
                        if parsed_date.year != 2025:
                            all_dates_ok = False
                            issue = f"Date hors 2025 trouvée dans 'Detailed Expenses': {date_val} (Ligne {index + 2})"
                            analysis_result["issues_identified"].append(issue)
                            print(f"ERREUR: {issue}")
                            analysis_result["dates_in_2025"] = False
                            # On peut arrêter la vérification des dates si une est fausse
                            # break 
                    except (ValueError, TypeError) as date_error:
                        all_dates_ok = False
                        issue = f"Format de date invalide dans 'Detailed Expenses': '{date_val}' (Ligne {index + 2}). Erreur: {date_error}"
                        analysis_result["issues_identified"].append(issue)
                        print(f"ERREUR: {issue}")
                        analysis_result["dates_in_2025"] = False
                        # break

                if all_dates_ok:
                    print("OK: Toutes les dates dans 'Detailed Expenses' sont en 2025.")
                else:
                     print("ERREUR: Au moins une date invalide ou hors 2025 trouvée dans 'Detailed Expenses'.")

                # Comparer la somme détaillée avec le total dépensé du Summary
                if analysis_result["excel_total_spent"] is not None:
                     if not np.isclose(total_detailed_spent, analysis_result["excel_total_spent"], rtol=1e-5):
                          issue = f"Incohérence entre le total dépensé de 'Budget Summary' ({analysis_result['excel_total_spent']}) et la somme de 'Detailed Expenses' ({total_detailed_spent})."
                          analysis_result["issues_identified"].append(issue)
                          analysis_result["detailed_expenses_total_matches"] = False
                          print(f"ERREUR: {issue}")
                     else:
                          print("OK: Somme 'Detailed Expenses' cohérente avec 'Budget Summary'.")
                          analysis_result["detailed_expenses_total_matches"] = True
                else:
                     issue = "Impossible de comparer la somme détaillée (total Budget Summary manquant)."
                     analysis_result["issues_identified"].append(issue)
                     analysis_result["detailed_expenses_total_matches"] = False
                     print(f"WARN: {issue}")

            else:
                 issue = f"Nombre de colonnes insuffisant dans l'onglet 'Detailed Expenses'. Attendu: {len(expected_cols_detail)}, Trouvé: {len(df_detailed.columns)}"
                 analysis_result["issues_identified"].append(issue)
                 print(f"ERREUR: {issue}")
                 analysis_result["completeness"] = "incomplete"

        except Exception as e:
            issue = f"Erreur lors de l'analyse de l'onglet 'Detailed Expenses': {e}"
            analysis_result["issues_identified"].append(issue)
            print(f"ERREUR: {issue}")
            traceback.print_exc()
            analysis_result["completeness"] = "incomplete"

    except FileNotFoundError:
        issue = f"Le fichier Excel n'a pas été trouvé: {excel_path}"
        analysis_result["issues_identified"].append(issue)
        print(f"ERREUR: {issue}")
        analysis_result["completeness"] = "incomplete"
        analysis_result["overall_conclusion"] = "Fichier Excel budget introuvable."
        return analysis_result
    except Exception as e:
        issue = f"Erreur générale lors de la lecture du fichier Excel {excel_path}: {e}"
        analysis_result["issues_identified"].append(issue)
        print(f"ERREUR: {issue}")
        traceback.print_exc()
        analysis_result["completeness"] = "incomplete"
        analysis_result["overall_conclusion"] = f"Erreur de lecture du fichier Excel: {e}"
        return analysis_result

    # --- Conclusion Finale --- 
    print("\n--- Fin de l'analyse du fichier budget --- ")
    if not analysis_result["issues_identified"]:
        analysis_result["completeness"] = "complete"
        analysis_result["quality_assessment"] = "high"
        analysis_result["overall_conclusion"] = "Analyse du budget terminée. Le fichier semble complet et cohérent."
        print("Conclusion: Fichier budget OK.")
    else:
        # Si on avait 'partial' et qu'on a trouvé des erreurs -> incomplete
        if analysis_result["completeness"] == "partial":
             analysis_result["completeness"] = "incomplete"
        analysis_result["quality_assessment"] = "medium" if analysis_result["completeness"] != "incomplete" else "low"
        analysis_result["overall_conclusion"] = f"Analyse du budget terminée. Problèmes détectés: {len(analysis_result['issues_identified'])}." + " Voir 'issues_identified' pour détails."
        print(f"Conclusion: Problèmes détectés ({len(analysis_result['issues_identified'])}). Voir logs.")

    return analysis_result

# --- Exemple d'utilisation --- 
if __name__ == '__main__':
    # Créer un fichier Excel de test (simulacre)
    # Dans un vrai scénario, on utiliserait un fichier téléchargé
    test_excel_path = "budget_test.xlsx"
    dummy_form_data = {
        'total_allocated': 5000,
        'amount_spent': 3550,
        'amount_already_paid': 1000,
        'remaining_amount': 2550
    }

    with pd.ExcelWriter(test_excel_path) as writer:
        # Budget Summary
        summary_df = pd.DataFrame([
            ("Project Name", "Test Project"),
            ("Campus", "Paris"),
            ("EOTP Code", "EOTP123"),
            ("Total Budget Allocated", 5000),
            ("Total Amount Spent", 3550),
            ("Amount Already Paid", 1000),
            ("Remaining Amount to Pay", 2550),
            ("Budget Period", "Year 2025")
        ], columns=['Field', 'Value'])
        summary_df.to_excel(writer, sheet_name='Budget Summary', index=False, header=False)

        # Expense Categories
        categories_df = pd.DataFrame([
            ("IT Equipment", 1000, 800, 200, "80.00%"),
            ("Personnel Costs", 2000, 1500, 500, "75.00%"),
            ("Travel & Events", 1500, 1250, 250, "83.33%"),
            ("Communication", 500, 0, 500, "0.00%"),
            ("TOTAL", 5000, 3550, 1450, "71.00%") # Ligne Total
        ], columns=["Expense Category", "Allocated Budget", "Actual Expenses", "Variance", "% Executed"])
        categories_df.to_excel(writer, sheet_name='Expense Categories', index=False)

        # Detailed Expenses
        detailed_df = pd.DataFrame([
            ("2025-01-15", "IT Equipment", "Laptop", "Supplier A", 800, "INV001"),
            ("2025-03-10", "Personnel Costs", "Salary Month 1", "Internal", 750, "PAY001"),
            ("2025-04-10", "Personnel Costs", "Salary Month 2", "Internal", 750, "PAY002"),
            ("2025-02-20", "Travel & Events", "Train Tickets", "Supplier B", 250, "INV002"),
            ("2025-05-05", "Travel & Events", "Conference Fee", "Org C", 1000, "INV003"),
            # Erreur potentielle: date hors 2025
            # ("2024-12-15", "Travel & Events", "Early Booking", "Org D", 100, "INV004")
        ], columns=["Date", "Expense Category", "Description", "Supplier", "Amount", "Invoice Reference"])
        # Forcer la colonne Date en type datetime pour le test
        detailed_df['Date'] = pd.to_datetime(detailed_df['Date'])
        detailed_df.to_excel(writer, sheet_name='Detailed Expenses', index=False)

    print(f"Fichier Excel de test créé: {test_excel_path}")

    # Lancer l'analyse
    analysis_output = analyse_budget_excel(test_excel_path, dummy_form_data)

    # Afficher le résultat (format JSON simulé)
    import json
    print("\n--- Résultat de l'analyse (JSON) ---")
    print(json.dumps(analysis_output, indent=2))

    # Nettoyage (optionnel)
    # import os
    # os.remove(test_excel_path) 