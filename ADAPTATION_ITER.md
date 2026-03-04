# Adaptation du projet DIT vers le contexte ITER (I – IMT – EEA)

## 1) Le sujet est-il le même ?

**Oui, le sujet est très proche, mais pas totalement identique.**

Points communs :
- Évaluation des enseignements et des enseignants par les étudiants.
- Collecte des réponses via une application web.
- Production de statistiques (moyennes, synthèses).
- Besoin de confidentialité des données.

Différences clés à couvrir pour ITER :
- Le besoin ITER inclut explicitement **l’organisation des cours** et **les infrastructures pédagogiques**.
- Le besoin ITER demande des **rapports par filière** (I, IMT, EEA).
- Le besoin ITER insiste sur l’**anonymat garanti** et l’**aide à la décision** (indicateurs plus orientés pilotage).

## 2) Ce que le dépôt actuel couvre déjà

Le dépôt actuel fournit déjà une base solide :
- Formulaire d’évaluation avec notes/commentaires.
- Association classe/matière.
- Espace administrateur.
- Calcul d’indicateurs agrégés (moyennes, oui/non).
- Stack exploitable en projet tutoré (Flask + SQLAlchemy + Docker/Jenkins).

## 3) Écarts entre l’existant et le cahier des charges ITER

### A. Modélisation institutionnelle
**Écart :** pas de notion explicite de filière (I/IMT/EEA), semestre, UE, enseignant identifié.

**Adaptation recommandée :**
- Ajouter des entités : `Filiere`, `Enseignant`, `UE` (ou `Cours`), `Semestre`.
- Relier chaque réponse à une filière + UE + enseignant + période.

### B. Anonymat réellement garanti
**Écart :** le système repose sur la session web ; pas de mécanisme robuste d’anonymisation contrôlée.

**Adaptation recommandée :**
- Introduire un système de **jetons d’évaluation à usage unique** (token non nominatif).
- Journaliser uniquement l’état du token (utilisé/non utilisé), sans lier identité ↔ réponse.
- Séparer techniquement tables d’authentification et tables de réponses.

### C. Couverture des dimensions d’évaluation ITER
**Écart :** certains critères existent, mais la structure n’est pas explicitement segmentée en
enseignements / enseignant / organisation / infrastructures.

**Adaptation recommandée :**
- Structurer le questionnaire en 4 blocs :
  1. Enseignement (contenu, charge, progressivité)
  2. Enseignant (clarté, disponibilité, méthode)
  3. Organisation (emploi du temps, coordination, communication)
  4. Infrastructures (salles, équipements, réseau, plateformes)

### D. Indicateurs décisionnels
**Écart :** agrégats de base présents, mais peu d’indicateurs de pilotage.

**Adaptation recommandée :**
- Ajouter des indicateurs :
  - Score global par filière / UE / enseignant.
  - Taux de satisfaction par thème.
  - Top 3 points forts / Top 3 points à améliorer (analyse commentaires).
  - Évolution temporelle (semestre N vs N-1).

### E. Gouvernance et sécurité
**Écart :** secrets applicatifs en dur dans le code, gestion admin minimale.

**Adaptation recommandée :**
- Déplacer secrets/identifiants dans variables d’environnement.
- Ajouter rôles (`admin`, `chef_departement`, `responsable_filiere`).
- Activer journalisation d’audit des actions administratives.

## 4) Plan d’adaptation par étapes (projet tutoré)

### Étape 1 — Cadrage fonctionnel (1 semaine)
- Définir questionnaire final validé par ITER.
- Définir rôles et droits.
- Définir les rapports attendus par filière.

### Étape 2 — Modèle de données (1 semaine)
- Étendre le schéma : filières, enseignants, UE, campagnes d’évaluation.
- Préparer migrations de base de données.

### Étape 3 — Collecte anonyme (1 à 2 semaines)
- Implémenter tokens anonymes à usage unique.
- Créer workflow de campagne (ouverture/fermeture).

### Étape 4 — Restitution analytique (1 à 2 semaines)
- Tableaux de bord par filière/UE/enseignant.
- Export PDF/Excel consolidé.

### Étape 5 — Sécurisation & industrialisation (1 semaine)
- Gestion secrets, durcissement auth, audit.
- Tests + conteneurisation + déploiement.

## 5) Proposition de livrables pour votre soutenance

- **Spécification fonctionnelle ITER** (questionnaire + règles d’anonymat).
- **Schéma de données cible** (MCD/MLD + dictionnaire).
- **Prototype web** avec campagne d’évaluation active.
- **Dashboard décisionnel** (captures + exports).
- **Bilan sécurité/RGPD local** (données collectées, conservation, accès).

## 6) Conclusion

Vous pouvez **réutiliser ce repository comme base technique**, car il traite déjà le cœur du besoin
(collecte + statistiques + administration). En revanche, pour répondre exactement au sujet ITER,
il faut **renforcer l’anonymat, introduire la granularité par filière, et produire des indicateurs de pilotage**.

En bref : **même famille de sujet, adaptation nécessaire mais tout à fait faisable**.
