from app import app, db, Classe, Matiere

def init_db():
    with app.app_context():
        # Supprimer et recréer toutes les tables
        db.drop_all()
        db.create_all()

        # Ajouter des données d'exemple
        classes = ['L1', 'L2', 'L3']
        matieres = ['Algorithmique', 'Bases de Données', 'Réseaux', 'Électronique']

        for nom in classes:
            db.session.add(Classe(nom=nom))
        for nom in matieres:
            db.session.add(Matiere(nom=nom))

        db.session.commit()
        print("Base de données initialisée avec succès.")

if __name__ == "__main__":
    init_db()
