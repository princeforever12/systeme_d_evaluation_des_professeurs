import unittest

from app import app, db, Classe, Matiere, AuditLog, run_schema_updates


class Phase5SecurityAuditTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        with app.app_context():
            db.drop_all()
            db.create_all()
            run_schema_updates()
            if not Classe.query.first():
                db.session.add(Classe(nom='L2 I'))
            if not Matiere.query.first():
                db.session.add(Matiere(nom='Algorithmique'))
            db.session.commit()

    def setUp(self):
        self.client = app.test_client()

    def test_health_endpoint(self):
        res = self.client.get('/health')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'"status":"ok"', res.data)

    def test_admin_login_writes_audit(self):
        res = self.client.post('/login', data={'username': 'admin', 'password': 'adminpassword'}, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        with app.app_context():
            latest = AuditLog.query.order_by(AuditLog.id.desc()).first()
            self.assertIsNotNone(latest)
            self.assertEqual(latest.action, 'admin_login')


if __name__ == '__main__':
    unittest.main()
