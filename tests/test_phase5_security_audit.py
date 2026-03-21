import unittest

from app import (
    app,
    db,
    Classe,
    Matiere,
    AuditLog,
    Teacher,
    EvaluationCampaign,
    EvaluationToken,
    ClassQuestion,
    SurveyResponse,
    ClassQuestionAnswer,
    run_schema_updates,
)


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
            'teacher_password': 'secret123',
            'teacher_subject_name': 'Algorithmique',
        }, follow_redirects=True)
        self.assertEqual(add_resp.status_code, 200)

        with app.app_context():
            t = Teacher.query.filter_by(username='mme.test').first()
            self.assertIsNotNone(t)
            self.assertTrue(t.is_active)
            self.assertEqual(t.assigned_subject_name, 'Algorithmique')

        login_resp = self.client.post('/teacher/login', data={
            'username': 'mme.test',
            'password': 'secret123'
        }, follow_redirects=True)
        self.assertEqual(login_resp.status_code, 200)
        self.assertIn(b'Dashboard Enseignant', login_resp.data)



    def test_l1_class_does_not_require_filiere_for_token_validation(self):
        with app.app_context():
            if not Classe.query.filter_by(nom='Licence 1').first():
                db.session.add(Classe(nom='Licence 1'))
            mat = Matiere.query.first()
            camp = EvaluationCampaign(name='Campagne L1', filiere_name='L1 (sans filière)', is_active=True)
            db.session.add(camp)
            db.session.flush()
            token = EvaluationToken(token='L1TOKEN0001', filiere_name='L1 (sans filière)', class_name='Licence 1', subject_name=mat.nom, is_used=False, campaign_id=camp.id)
            db.session.add(token)
            db.session.commit()

        with app.app_context():
            l1_id = Classe.query.filter_by(nom='Licence 1').first().id
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

    def test_admin_can_delete_campaign(self):
        with app.app_context():
            matiere = Matiere.query.first()
            if not Classe.query.filter_by(nom='L2 IMT').first():
                db.session.add(Classe(nom='L2 IMT'))
                db.session.commit()
            classe = Classe.query.filter_by(nom='L2 IMT').first()
            campaign = EvaluationCampaign(name='A supprimer', filiere_name='IMT', is_active=False)
            db.session.add(campaign)
            db.session.flush()
            db.session.add(EvaluationToken(
                token='DELTOKEN11',
                filiere_name='IMT',
                class_name=classe.nom,
                subject_name=matiere.nom,
                is_used=False,
                campaign_id=campaign.id,
            ))
            db.session.commit()
            campaign_id = campaign.id

        with self.client.session_transaction() as sess:
            sess['admin'] = True
            sess['username'] = 'admin'

        res = self.client.post(f'/delete_campaign/{campaign_id}', follow_redirects=True)
        self.assertEqual(res.status_code, 200)

        with app.app_context():
            self.assertIsNone(EvaluationCampaign.query.get(campaign_id))
            removed_token = EvaluationToken.query.filter_by(token='DELTOKEN11').first()
            self.assertIsNone(removed_token)

    def test_teacher_assigned_subject_only(self):
        with app.app_context():
            if not Matiere.query.filter_by(nom='Bases de donnees').first():
                db.session.add(Matiere(nom='Bases de donnees'))
                db.session.commit()

            SurveyResponse.query.delete()
            db.session.add(SurveyResponse(
                filiere_name='I',
                class_name='L2 I',
                subject_name='Algorithmique',
                involvement=0,
                initial_knowledge=0,
                current_knowledge=0,
                professor_motivation=0,
                tools_methodology=0,
                examples_exercises=0,
                explanations_clarity=0,
                practical_skills='non',
                course_organization='non',
                schedule_organization=0,
                infrastructure_quality=0,
                overall_satisfaction=0,
                feedback='algo',
            ))
            db.session.add(SurveyResponse(
                filiere_name='I',
                class_name='L2 I',
                subject_name='Bases de donnees',
                involvement=0,
                initial_knowledge=0,
                current_knowledge=0,
                professor_motivation=0,
                tools_methodology=0,
                examples_exercises=0,
                explanations_clarity=0,
                practical_skills='non',
                course_organization='non',
                schedule_organization=0,
                infrastructure_quality=0,
                overall_satisfaction=0,
                feedback='bdd',
            ))
            db.session.commit()

        # Recreate account with a real hash through the admin endpoint
        with self.client.session_transaction() as sess:
            sess['admin'] = True
            sess['username'] = 'admin'
        self.client.post('/add_teacher', data={
            'teacher_full_name': 'Prof BDD',
            'teacher_username': 'prof.bdd2',
            'teacher_password': 'secret123',
            'teacher_subject_name': 'Bases de donnees',
        }, follow_redirects=True)

        login_resp = self.client.post('/teacher/login', data={
            'username': 'prof.bdd2',
            'password': 'secret123',
        }, follow_redirects=True)
        self.assertEqual(login_resp.status_code, 200)
        self.assertIn(b'Mati\xc3\xa8re assign\xc3\xa9e', login_resp.data)
        self.assertIn(b'Bases de donnees', login_resp.data)
        self.assertNotIn(b'Algorithmique', login_resp.data)

    def test_admin_can_delete_completed_survey(self):
        with app.app_context():
            response = SurveyResponse(
                filiere_name='I',
                class_name='L2 I',
                subject_name='Algorithmique',
                involvement=0,
                initial_knowledge=0,
                current_knowledge=0,
                professor_motivation=0,
                tools_methodology=0,
                examples_exercises=0,
                explanations_clarity=0,
                practical_skills='non',
                course_organization='non',
                schedule_organization=0,
                infrastructure_quality=0,
                overall_satisfaction=0,
                feedback='to delete',
            )
            db.session.add(response)
            db.session.flush()
            db.session.add(ClassQuestionAnswer(
                survey_response_id=response.id,
                class_name='L2 I',
                question_text='Q',
                response_type='text',
                answer_value='A',
            ))
            db.session.commit()
            response_id = response.id

        with self.client.session_transaction() as sess:
            sess['admin'] = True
            sess['username'] = 'admin'

        delete_resp = self.client.post(f'/delete_survey_response/{response_id}', follow_redirects=True)
        self.assertEqual(delete_resp.status_code, 200)

        with app.app_context():
            self.assertIsNone(SurveyResponse.query.get(response_id))
            self.assertEqual(ClassQuestionAnswer.query.filter_by(survey_response_id=response_id).count(), 0)

if __name__ == '__main__':
    unittest.main()
