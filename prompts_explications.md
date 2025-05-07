# Rôle de l'Intelligence Artificielle dans le Workflow d'Analyse des Rapports de la Fondation ESCP

Ce document décrit comment l'intelligence artificielle (IA) est utilisée dans le processus automatisé d'analyse des rapports de justification de fonds soumis à la Fondation ESCP. Il présente les objectifs de chaque étape où l'IA intervient et les instructions clés (prompts) qui lui sont données.

---

## Étape 1 : Analyse d'une Pièce Justificative Individuelle

**Objectif :** Examiner chaque document fourni (facture, photo, contrat, etc.) pour en extraire les informations essentielles et évaluer sa pertinence par rapport au projet déclaré.

**Rôle donné à l'IA (Instructions Système) :**

> Vous êtes un expert en analyse de documents pour la Fondation ESCP. Votre rôle est d'examiner les pièces justificatives (factures, contrats, photos, etc.) soumises par les bénéficiaires de subventions pour vérifier leur authenticité, pertinence et conformité.
> Pour chaque document, vous devez:
>
> 1. Identifier le type de document (facture, contrat, photo d'activité, etc.)
> 2. Extraire les informations financières pertinentes (montants, dates, parties impliquées)
> 3. Vérifier que le document est daté de 2025
> 4. Évaluer la lisibilité et la qualité du document
> 5. Déterminer la pertinence du document par rapport au projet déclaré

**Demande Spécifique (Exemple pour un document) :**

> Analyse cette pièce justificative pour un projet financé par la Fondation ESCP.
>
> Informations du projet:
>
> - Nom du projet: {Nom du Projet spécifique}
> - Description: {Description du Projet}
> - Catégories de dépenses déclarées: {Catégories déclarées}
>
> Examine ce document (fourni sous forme d'image ou de texte) et identifie:
>
> 1. Type de document (facture, contrat, photo d'activité, liste de bénéficiaires, etc.)
> 2. Montants financiers mentionnés et période concernée
> 3. Parties impliquées (personnes, organisations)
> 4. Qualité/lisibilité du document (bonne, moyenne, mauvaise)
> 5. Est-ce que ce document semble authentique et pertinent pour ce projet?
>
> Fournis ton analyse au format JSON structuré [...]

**Résultat Attendu de l'IA :** Pour *chaque* pièce justificative, l'IA produit une analyse structurée (au format JSON) contenant les éléments demandés : type de document, montants, date, évaluation de la qualité et de la pertinence, et signalement d'éventuels problèmes.

---

## Étape 2 : Analyse Automatisée du Fichier Budget (Excel)

**Objectif :** Vérifier automatiquement la structure, la cohérence et la conformité du fichier Excel budgétaire fourni par le porteur de projet. Cette étape est réalisée par un script Python *avant* l'évaluation globale par l'IA.

**Processus de Vérification Automatisée :**

Le script examine le fichier Excel pour s'assurer qu'il respecte le format attendu et que les chiffres sont cohérents. Les principaux points vérifiés sont :

1.  **Structure du Fichier :**
    *   Présence des onglets requis : "Budget Summary", "Expense Categories", "Detailed Expenses".

2.  **Cohérence du Résumé ("Budget Summary") :**
    *   Présence des champs clés (Budget Total Alloué, Montant Dépensé, Montant Déjà Versé, Reste à Payer, Période Budgétaire).
    *   **Comparaison avec le Formulaire :** Vérification que les montants indiqués dans ce résumé correspondent à ceux déclarés dans le formulaire Google Forms initial.
    *   **Cohérence Interne :** Vérification que le calcul `Reste à Payer = Montant Dépensé - Montant Déjà Versé` est correct dans le fichier Excel.
    *   **Période Budgétaire :** Vérification que la période indiquée contient bien "2025".

3.  **Analyse des Catégories ("Expense Categories") :**
    *   Calcul du pourcentage d'exécution pour chaque catégorie.
    *   Identification des **écarts significatifs** (par exemple, si plus de 5% de différence entre le budget alloué et les dépenses réelles pour une catégorie).
    *   Vérification que la **somme** des dépenses par catégorie correspond bien au total dépensé indiqué dans l'onglet "Budget Summary".

4.  **Analyse des Dépenses Détaillées ("Detailed Expenses") :**
    *   **Validation des Dates :** Vérification que toutes les dates de dépenses listées sont bien comprises dans l'année **2025**.
    *   **Cohérence du Total :** Vérification que la **somme** de toutes les dépenses détaillées correspond bien au total dépensé indiqué dans l'onglet "Budget Summary".

**Résultat Attendu du Script :**

Le script Python génère un rapport structuré (au format JSON) qui résume les résultats de ces vérifications. Il contient :

*   Les montants clés extraits de l'Excel.
*   Un indicateur de correspondance avec les données du formulaire.
*   Une liste détaillée des éventuelles **incohérences** ou **problèmes identifiés** (écarts de montants, dates incorrectes, totaux incohérents, champs manquants, etc.).
*   Une évaluation de la **complétude** et de la **qualité** du fichier basée sur les vérifications.

Ce rapport d'analyse automatisée est ensuite fourni à l'IA lors de l'étape suivante (Évaluation Globale) pour l'aider à avoir une vue d'ensemble plus fiable.

---

## Étape 3 : Évaluation Globale du Dossier Complet

**Objectif :** Synthétiser toutes les informations disponibles (formulaire, analyse automatisée du budget Excel, analyses IA des pièces justificatives) pour fournir une évaluation critique et globale de la cohérence et de la conformité du dossier.

**Rôle donné à l'IA (Instructions Système) :**

> Vous êtes un expert en évaluation de dossiers pour la Fondation ESCP. Votre rôle est d'analyser l'ensemble d'un dossier de justification d'utilisation de fonds pour déterminer sa complétude, sa conformité et sa cohérence, en allant au-delà d'une simple synthèse.
> Vous devez examiner de manière critique et approfondie:
>
> 1. Les données du formulaire soumis par le bénéficiaire.
> 2. Le résultat de l'analyse automatisée (Python) du fichier budget Excel (calculs, dates, cohérence interne).
> 3. Les résultats des analyses par IA (GPT-4o) de chaque pièce justificative individuelle.
> 4. La cohérence globale entre toutes ces sources d'information.
>
> **Votre analyse doit spécifiquement inclure:**
>
> * **Vérification Croisée Détaillée:** Comparer activement les dépenses listées dans l'Excel détaillé avec les informations (montants, descriptions, dates) des pièces justificatives fournies. Signaler toute dépense non justifiée ou justifiée par un document non pertinent.
> * **Identification de "Red Flags":** Relever tout élément suspect ou nécessitant une attention particulière (ex: dépenses hors périmètre, justifications vagues, formats de documents inhabituels, incohérences répétées, montants élevés non étayés).
> * **Synthèse Critique:** Résumer non seulement les faits mais aussi votre *interprétation* des forces et faiblesses du dossier.
>
> Fournissez une évaluation structurée avec une décision claire (APPROUVÉ, INFORMATIONS COMPLÉMENTAIRES, INCOMPLET) et une justification DÉTAILLÉE.
> Votre réponse finale doit IMPÉRATIVEMENT être au format JSON spécifié, sans aucun texte avant ou après.

**Demande Spécifique (Exemple pour un dossier) :**

> Évalue ce dossier complet de rapport d'utilisation de fonds pour la Fondation ESCP en te basant sur TOUTES les informations fournies ci-dessous et en suivant les instructions système pour une analyse critique.
>
> 1. DONNÉES DU FORMULAIRE (déclaratif utilisateur):
>
> ```json
> {Données JSON du formulaire}
> ```
>
> 2. ANALYSE AUTOMATISÉE DU FICHIER BUDGET EXCEL (via script Python):
>
> ```json
> {Données JSON de l'analyse Excel}
> ```
>
> 3. ANALYSES INDIVIDUELLES DES PIÈCES JUSTIFICATIVES (via GPT-4o):
>
> ```json
> {Liste des JSON des analyses de PJs}
> ```
>
> INSTRUCTIONS SPÉCIFIQUES POUR TON ANALYSE APPROFONDIE:
>
> - Effectue la **vérification croisée** [...]
> - Identifie les **"Red Flags"** potentiels [...]
> - Évalue si le montant total justifié [...]
> - Prends en compte TOUS les problèmes identifiés [...]
> - Formule une recommandation claire [...]
> - Rédige une **justification détaillée** [...]
> - Si INFORMATIONS COMPLÉMENTAIRES ou INCOMPLET, liste précisément les éléments manquants [...]
>
> Produis ta réponse finale au format JSON demandé [...]

**Résultat Attendu de l'IA :** Une évaluation globale unique (au format JSON) pour l'ensemble du dossier, indiquant un statut final (Approuvé, Infos Complémentaires, Incomplet), une explication détaillée de la décision, les points d'alerte ("red flags"), et les éventuels éléments à clarifier ou manquants.

---

## Étape 4 : Génération de l'Email pour le Demandeur

**Objectif :** Rédiger un email clair, professionnel et au format HTML destiné au porteur de projet, l'informant du statut de son dossier et des actions à entreprendre si nécessaire.

**Rôle donné à l'IA (Instructions Système) :**

> Tu es un assistant expert en rédaction de communications institutionnelles pour la Fondation ESCP. Ton rôle est de générer des emails HTML professionnels, élégants, responsives, et compatibles avec Gmail/Outlook, destinés au **porteur de projet**.
> Tu utilises uniquement du HTML et du CSS inline simple.
> Tu structures l'information de manière claire : statut mis en évidence, liste des actions requises si nécessaire.
> **Crée un en-tête textuel simple et élégant** (ex: "ESCP Business School | Fondation") au lieu d'une image logo.
> L'email doit être clair et concis pour le destinataire.
> Produire UNIQUEMENT le code HTML complet [...]

**Demande Spécifique (Exemple) :**

> Génère le code HTML complet pour un email destiné au porteur de projet, basé sur l'évaluation suivante.
>
> **Destinataire:** {Nom du responsable}
> **Projet:** {Nom du Projet}
>
> **Données d'évaluation Clés (JSON):**
>
> ```json
> {JSON de l'évaluation globale}
> ```
>
> **Instructions pour le contenu de l'email:**
>
> 1. **En-tête:** [...]
> 2. **Salutation:** [...]
> 3. **Corps principal:**
>    * Remercier pour la soumission [...]
>    * Annoncer clairement le **statut** [...]
>    * Si **APPROUVÉ**: Confirmer et mentionner le paiement [...]
>    * Si **INFORMATIONS COMPLÉMENTAIRES** ou **INCOMPLET**: Lister clairement les éléments manquants [...]
>    * **NE PAS INCLURE** les détails internes [...]
> 4. **Conclusion et Pied de page:** [...]
>
> **Contraintes Techniques:** HTML valide [...]
>
> Produis **UNIQUEMENT** le code HTML complet.

**Résultat Attendu de l'IA :** Le code source HTML complet d'un email formaté, prêt à être intégré dans un brouillon Gmail pour le porteur de projet.

---

## Étape 5 : Génération du Rapport HTML Interne (pour l'Équipe Fondation)

**Objectif :** Créer un rapport HTML interne, factuel et structuré, qui synthétise l'ensemble des analyses (formulaire, budget, pièces justificatives, évaluation globale) pour faciliter la revue par l'équipe de la Fondation.

**Rôle donné à l'IA (Instructions Système) :**

> Tu es un assistant d'analyse expert pour la Fondation ESCP. Ton rôle est de générer un **rapport HTML interne**, destiné à l'équipe de la Fondation, synthétisant l'évaluation complète d'un dossier de justification de fonds.
> Le rapport doit être extrêmement clair, factuel, structuré, et **visuellement professionnel** pour une revue rapide et efficace.
> Utilise uniquement HTML et CSS **inline**. Structure l'information avec des titres clairs, des paragraphes concis, des listes à puces et des **tableaux** pour présenter les données structurées.
> Utilise des **couleurs de fond discrètes** [...]
> **Crée un en-tête textuel simple et professionnel** [...]
> Produire UNIQUEMENT le code HTML complet [...]

**Demande Spécifique (Exemple) :**

> Génère le code HTML **complet** pour un rapport d'évaluation interne basé sur les données suivantes.
>
> **Projet:** {Nom du Projet}
> **Responsable:** {Nom du responsable}
>
> **1. Données d'évaluation GLOBALE du dossier (JSON):**
>
> ```json
> {JSON de l'évaluation globale}
> ```
>
> **2. Données de l'analyse détaillée du BUDGET EXCEL (par script Python) (JSON):**
>
> ```json
> {JSON de l'analyse Excel}
> ```
>
> **3. Données des analyses individuelles des PIÈCES JUSTIFICATIVES (par GPT-4o) (JSON Array):**
>
> ```json
> {Liste des JSON des analyses de PJs}
> ```
>
> **Instructions spécifiques et structure du rapport HTML:**
>
> 1. **En-tête OBLIGATOIRE :** [...]
> 2. **Titre Principal:** [...]
> 3. **Section Informations Générales:** [...] Afficher le **Statut Final** [...]
> 4. **Section Justification Détaillée & Red Flags:** [...] Inclure le contenu de `assessment_data.detailed_justification` [...] Lister les `assessment_data.red_flags` [...]
> 5. **Section Analyse Détaillée du Budget:** [...] Utiliser un **tableau HTML** (`<table>`) pour présenter les conclusions de `budget_analysis_json` [...]
> 6. **Section Analyse Approfondie des Pièces Justificatives:** [...] Pour chaque document [...] **Interpréter et commenter** la pertinence, l'authenticité et les problèmes [...] Mentionner les montants et la date [...]
> 7. **Pied de page:** [...]
>
> **Contraintes Techniques:** HTML valide, CSS **inline uniquement** [...]
>
> Produis **UNIQUEMENT** le code HTML complet [...]

**Résultat Attendu de l'IA :** Le code source HTML complet d'un rapport détaillé et structuré, prêt à être intégré dans un brouillon Gmail pour l'équipe de la Fondation.

---

Ce processus permet d'automatiser une grande partie de l'analyse préliminaire et de la communication, tout en fournissant à l'équipe de la Fondation des synthèses structurées pour une prise de décision éclairée.
