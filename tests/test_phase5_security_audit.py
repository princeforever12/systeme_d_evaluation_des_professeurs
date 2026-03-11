import unittest

from app import app, db, Classe, Matiere, AuditLog, Teacher, EvaluationCampaign, EvaluationToken, ClassQuestion, run_schema_updates


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



    def test_l1_class_does_not_require_filiere_for_token_validation(self):
        with app.app_context():
            if not Classe.query.filter_by(nom='L1').first():
                db.session.add(Classe(nom='L1'))
            mat = Matiere.query.first()
            camp = EvaluationCampaign(name='Campagne L1', filiere_name='L1 (sans filière)', is_active=True)
            db.session.add(camp)
            db.session.flush()
            token = EvaluationToken(token='L1TOKEN0001', filiere_name='L1 (sans filière)', class_name='L1', subject_name=mat.nom, is_used=False, campaign_id=camp.id)
            db.session.add(token)
            db.session.commit()

        with app.app_context():
            l1_id = Classe.query.filter_by(nom='L1').first().id
            matiere_id = Matiere.query.first().id

        resp = self.client.post('/class_subject', data={
            'filiere': '',
            'classe': str(l1_id),
            'matiere': str(matiere_id),
            'access_token': 'L1TOKEN0001'
        }, follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/survey', resp.headers.get('Location', ''))

    def test_class_specific_text_question_is_required(self):
        with app.app_context():
            classe = Classe.query.filter_by(nom='L2 I').first()
            mat = Matiere.query.first()
            q = ClassQuestion(class_name='L2 I', question_text='Que faut-il améliorer ?', response_type='text')
            camp = EvaluationCampaign(name='Campagne L2', filiere_name='I', is_active=True)
            db.session.add_all([q, camp])
            db.session.flush()
            token = EvaluationToken(token='TOKENTEST22', filiere_name='I', class_name=classe.nom, subject_name=mat.nom, is_used=False, campaign_id=camp.id)
            db.session.add(token)
            db.session.commit()

        with app.app_context():
            subject_name = Matiere.query.first().nom
            token_id = EvaluationToken.query.filter_by(token='TOKENTEST22').first().id
            class_question_id = ClassQuestion.query.filter_by(class_name='L2 I').first().id

        with self.client.session_transaction() as sess:
            sess['filiere_name'] = 'I'
            sess['class_name'] = 'L2 I'
            sess['subject_name'] = subject_name
            sess['token_id'] = token_id

        data = {
            'feedback': 'ok',
            f'class_question_{class_question_id}': ''
        }
        resp = self.client.post('/survey', data=data, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Que faut-il am', resp.data)

        with app.app_context():
            token = EvaluationToken.query.filter_by(token='TOKENTEST22').first()
            self.assertFalse(token.is_used)

if __name__ == '__main__':
    unittest.main()
