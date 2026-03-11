import unittest

from app import app, db, Classe, Matiere, AuditLog, Teacher, run_schema_updates


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

    def test_teacher_login_and_dashboard(self):
        res = self.client.post('/teacher/login', data={'username': 'enseignant', 'password': 'enseignantpassword'}, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Dashboard Enseignant', res.data)

        with app.app_context():
            latest = AuditLog.query.order_by(AuditLog.id.desc()).first()
            self.assertIsNotNone(latest)
            self.assertEqual(latest.action, 'teacher_login')

    def test_admin_audit_page_requires_admin_and_loads(self):
        denied = self.client.get('/admin/audit', follow_redirects=False)
        self.assertEqual(denied.status_code, 302)

        with self.client.session_transaction() as sess:
            sess['admin'] = True
            sess['username'] = 'admin'

        ok = self.client.get('/admin/audit')
        self.assertEqual(ok.status_code, 200)
        self.assertIn(b"Journal d'audit", ok.data)

    def test_admin_can_add_teacher_and_teacher_can_login(self):
        with self.client.session_transaction() as sess:
            sess['admin'] = True
            sess['username'] = 'admin'

        add_resp = self.client.post('/add_teacher', data={
            'teacher_full_name': 'Mme Test',
            'teacher_username': 'mme.test',
            'teacher_password': 'secret123'
        }, follow_redirects=True)
        self.assertEqual(add_resp.status_code, 200)

        with app.app_context():
            t = Teacher.query.filter_by(username='mme.test').first()
            self.assertIsNotNone(t)
            self.assertTrue(t.is_active)

        login_resp = self.client.post('/teacher/login', data={
            'username': 'mme.test',
            'password': 'secret123'
        }, follow_redirects=True)
        self.assertEqual(login_resp.status_code, 200)
        self.assertIn(b'Dashboard Enseignant', login_resp.data)


if __name__ == '__main__':
    unittest.main()
