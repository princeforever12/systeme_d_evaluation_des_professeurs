# 🎓 Système Web d’Évaluation des Enseignements - UTT-LOKO (ITER)  

## 📖 Aperçu  
Base applicative initialement inspirée d'un cas DIT, maintenant adaptée au **Département ITER de l'UTT-LOKO** pour :  
- **Remplacer Typeform** (limités en contrôle des données et analyses).  
- **Automatiser** la collecte et l'analyse des évaluations enseignants/cours.  
- **Garantir la confidentialité** (données hébergées en interne).  

## 🛠 Fonctionnalités  
### Pour les Étudiants  
- Évaluation des cours via interface simplifiée (notes/commentaires).  
- Sélection dynamique des **filières (I/IMT/EEA)**, classes et matières.  

### Pour les Administrateurs  
- Génération de rapports PDF/Excel (stats agrégées, tendances).  
- Gestion des classes/matières et réinitialisation des sondages.  

## ⚙️ Architecture  
```mermaid  
graph TD  
    A[Flask Backend] --> B[(SQLite)]  
    A --> C[Frontend HTML/Tailwind]  
    D[Jenkins CI/CD] --> E[Docker Containers]  
    E --> F[Kubernetes Cluster]  


## 🔁 Adaptation au cahier des charges ITER
Un guide d’analyse et de migration vers le contexte **Département ITER (I/IMT/EEA)** est disponible ici :
- `ADAPTATION_ITER.md`


## ✅ Adaptation déjà implémentée (phase 1)
- Rebranding UTT-LOKO / ITER dans l'interface.
- Ajout de la sélection de filière côté étudiant et administration.
- Filtrage des rapports par filière + classe + matière.


## 📌 Documentation projet tutoré (phase 2)
- `CAHIER_DES_CHARGES_V1.md`
- `PLAN_GESTION_PROJET_V1.md`


## ✅ Adaptation déjà implémentée (phase 3)
- Campagnes d'évaluation par filière (création + activation).
- Génération de tokens anonymes à usage unique par filière/classe/matière.
- Accès au questionnaire conditionné par token valide et campagne active.
