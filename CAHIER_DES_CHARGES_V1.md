# Cahier des charges fonctionnel (V1)
## Projet tutoré L2 — Système Web d'Évaluation des Enseignements
### UTT-LOKO — Département ITER (I / IMT / EEA)

## 1. Contexte
Le département ITER souhaite centraliser les évaluations des enseignements, des enseignants, de l'organisation des cours et des infrastructures pédagogiques via une plateforme web.

## 2. Objectifs
- Collecter les évaluations des étudiants par filière, classe et matière.
- Préserver l'anonymat des réponses.
- Générer des indicateurs statistiques par filière.
- Fournir des rapports exploitables par l'administration pédagogique.

## 3. Périmètre fonctionnel V1
### 3.1 Étudiant
- Sélection de la filière (I / IMT / EEA), classe et matière.
- Saisie d'un questionnaire structuré en 4 dimensions :
  1) Enseignement
  2) Enseignant
  3) Organisation
  4) Infrastructures
- Soumission d'une réponse anonyme.

### 3.2 Administration
- Gestion des classes et matières.
- Consultation des réponses.
- Génération de rapport par filière + classe + matière.

## 4. Données principales
- Filière
- Classe
- Matière
- Réponse d'évaluation
- Indicateurs agrégés (moyennes, taux de satisfaction)

## 5. Contraintes
- Application web responsive.
- Persistance SQLite (phase prototype).
- Sécurité minimale : authentification admin et gestion de session.

## 6. Critères d'acceptation V1
- Un étudiant peut soumettre une évaluation complète.
- Les notes d'organisation et d'infrastructures sont présentes dans le formulaire.
- L'admin peut obtenir un rapport filtré par filière.
