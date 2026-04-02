from datetime import datetime
import secrets
import string
import csv
import io
import os
import re

from flask import Flask, render_template, request, redirect, url_for, session, flash, Response, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'dev-secret-key-change-me')

# Configuration de la base de données
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

FILIERES_ITER = ['I', 'IMT', 'EEA']
L1_LABEL = 'L1 (sans filière)'
TRONC_COMMUN_LABEL = 'Tronc commun'
CAMPAIGN_GLOBAL_LABEL = 'ALL'
ALL_FILIERES = [L1_LABEL, TRONC_COMMUN_LABEL] + FILIERES_ITER
CLASS_LEVELS = ['L1', 'L2', 'L3']
DEFAULT_CLASSES = CLASS_LEVELS
VOLETS = ['enseignement', 'enseignant', 'organisation', 'infrastructures']
VOLET_LABELS = {
    'enseignement': 'Enseignement',
    'enseignant': 'Enseignants',
    'organisation': 'Organisation des cours',
    'infrastructures': 'Infrastructures pédagogiques',
}


def is_l1_class(class_name):
    if not class_name:
        return False
    normalized = class_name.strip().upper()
    return bool(re.search(r'\b(L\s*1|LICENCE\s*1|LICENSE\s*1)\b', normalized))


def normalize_filiere_for_class(class_name, filiere_name):
    class_name = (class_name or '').strip()
    filiere_name = (filiere_name or '').strip()

    if is_l1_class(class_name):
        return L1_LABEL
    if filiere_name in FILIERES_ITER or filiere_name == TRONC_COMMUN_LABEL:
        return filiere_name
    return None


# Modèles de base de données
class Classe(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(100), nullable=False)


class Matiere(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(100), nullable=False)
    class_name = db.Column(db.String(100), nullable=False, default='ALL')
    filiere_name = db.Column(db.String(30), nullable=False, default='ALL')


class EvaluationCampaign(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    filiere_name = db.Column(db.String(20), nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class EvaluationToken(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(20), unique=True, nullable=False)
    filiere_name = db.Column(db.String(20), nullable=False)
    class_name = db.Column(db.String(100), nullable=False)
    subject_name = db.Column(db.String(100), nullable=False)
    is_used = db.Column(db.Boolean, nullable=False, default=False)
    used_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    campaign_id = db.Column(db.Integer, db.ForeignKey('evaluation_campaign.id'), nullable=True)


class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    actor = db.Column(db.String(120), nullable=False)
    action = db.Column(db.String(120), nullable=False)
    details = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class Teacher(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(150), nullable=True)
    assigned_subject_name = db.Column(db.String(100), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class Questionnaire(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(180), nullable=False)
    description = db.Column(db.String(500), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class ClassQuestion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    class_name = db.Column(db.String(100), nullable=False)
    filiere_name = db.Column(db.String(30), nullable=False, default='ALL')
    volet_name = db.Column(db.String(30), nullable=False, default='enseignement')
    question_text = db.Column(db.String(300), nullable=False)
    response_type = db.Column(db.String(20), nullable=False, default='scale')
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class SurveyResponse(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filiere_name = db.Column(db.String(20), nullable=False, default='I')
    class_name = db.Column(db.String(50), nullable=False)
    subject_name = db.Column(db.String(50), nullable=False)
    involvement = db.Column(db.Integer, nullable=False)
    initial_knowledge = db.Column(db.Integer, nullable=False)
    current_knowledge = db.Column(db.Integer, nullable=False)
    professor_motivation = db.Column(db.Integer, nullable=False)
    tools_methodology = db.Column(db.Integer, nullable=False)
    examples_exercises = db.Column(db.Integer, nullable=False)
    explanations_clarity = db.Column(db.Integer, nullable=False)
    practical_skills = db.Column(db.String(3), nullable=False)
    course_organization = db.Column(db.String(3), nullable=False)
    schedule_organization = db.Column(db.Integer, nullable=False, default=0)
    infrastructure_quality = db.Column(db.Integer, nullable=False, default=0)
    overall_satisfaction = db.Column(db.Integer, nullable=False)
    feedback = db.Column(db.String(500), nullable=True)


class ClassQuestionAnswer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    survey_response_id = db.Column(db.Integer, db.ForeignKey('survey_response.id'), nullable=False)
    class_name = db.Column(db.String(100), nullable=False)
    question_text = db.Column(db.String(300), nullable=False)
    response_type = db.Column(db.String(20), nullable=False)
    answer_value = db.Column(db.String(500), nullable=False)


# Stockage sécurisé des mots de passe
ADMIN_USERNAME = os.getenv('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD_HASH = generate_password_hash(os.getenv('ADMIN_PASSWORD', 'adminpassword'))
TEACHER_USERNAME = os.getenv('TEACHER_USERNAME', 'enseignant')
TEACHER_PASSWORD_HASH = generate_password_hash(os.getenv('TEACHER_PASSWORD', 'enseignantpassword'))


def ensure_admin_session():
    if not session.get('admin'):
        flash('Veuillez vous connecter pour accéder à cette page.', 'danger')
        return False
    return True


def ensure_teacher_session():
    if not session.get('teacher'):
        flash('Veuillez vous connecter à l\'espace enseignant.', 'danger')
        return False
    return True


def log_audit(action, details=''):
    actor = session.get('username') or session.get('teacher_username') or 'anonymous'
    db.session.add(AuditLog(actor=actor, action=action, details=details[:500]))
    db.session.commit()


def generate_unique_token():
    alphabet = string.ascii_uppercase + string.digits
    while True:
        token = ''.join(secrets.choice(alphabet) for _ in range(10))
        if not EvaluationToken.query.filter_by(token=token).first():
            return token


def ensure_default_classes():
    existing_names = {c.nom for c in Classe.query.all()}
    missing = [name for name in DEFAULT_CLASSES if name not in existing_names]
    if missing:
        db.session.add_all([Classe(nom=name) for name in missing])
        db.session.commit()


def build_dashboard_query(filiere_name=None, classe_name=None, subject_name=None):
    query = SurveyResponse.query
    if filiere_name:
        query = query.filter_by(filiere_name=filiere_name)
    if classe_name:
        query = query.filter_by(class_name=classe_name)
    if subject_name:
        query = query.filter_by(subject_name=subject_name)
    return query


@app.route('/')
def home():
    return render_template('home.html')


@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'service': 'iter-eval-app'})


@app.route('/survey', methods=['GET', 'POST'])
def survey():
    filiere_name = session.get('filiere_name')
    class_name = session.get('class_name')
    subject_name = session.get('subject_name')
    token_id = session.get('token_id')

    if not (filiere_name and class_name and subject_name and token_id):
        flash("Veuillez d'abord sélectionner filière/classe/matière et fournir un token valide.", 'warning')
        return redirect(url_for('select'))

    token_obj = EvaluationToken.query.get(token_id)
    if not token_obj or token_obj.is_used:
        flash('Token invalide ou déjà utilisé.', 'danger')
        return redirect(url_for('select'))

    query = ClassQuestion.query.filter_by(class_name=class_name)
    if filiere_name == L1_LABEL:
        query = query.filter(ClassQuestion.filiere_name.in_([L1_LABEL, 'ALL']))
    else:
        query = query.filter(ClassQuestion.filiere_name.in_([filiere_name, TRONC_COMMUN_LABEL, 'ALL']))
    class_questions = query.order_by(ClassQuestion.created_at.asc()).all()
    questions_by_volet = {volet: [] for volet in VOLETS}
    for question in class_questions:
        volet = question.volet_name if question.volet_name in VOLETS else 'enseignement'
        questions_by_volet[volet].append(question)

    if request.method == 'POST':
        feedback = request.form.get('feedback', '').strip()
        extra_answers = []
        extra_errors = []

        for question in class_questions:
            field_name = f'class_question_{question.id}'
            value = request.form.get(field_name, '').strip()
            if question.response_type == 'scale':
                if value not in {str(i) for i in range(11)}:
                    extra_errors.append(f'Réponse manquante pour la question: {question.question_text}')
                else:
                    extra_answers.append((question, value))
            else:
                if not value:
                    extra_errors.append(f'Veuillez saisir une réponse pour: {question.question_text}')
                else:
                    extra_answers.append((question, value[:500]))

        if not extra_errors:
            new_response = SurveyResponse(
                filiere_name=filiere_name,
                class_name=class_name,
                subject_name=subject_name,
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
                feedback=feedback,
            )
            db.session.add(new_response)
            db.session.flush()

            for question, answer in extra_answers:
                db.session.add(ClassQuestionAnswer(
                    survey_response_id=new_response.id,
                    class_name=class_name,
                    question_text=question.question_text,
                    response_type=question.response_type,
                    answer_value=answer,
                ))

            token_obj.is_used = True
            token_obj.used_at = datetime.utcnow()
            db.session.commit()
            log_audit('survey_submitted', f'filiere={filiere_name}, classe={class_name}, matiere={subject_name}, extra_questions={len(extra_answers)}')
            session.pop('token_id', None)
            return redirect(url_for('result'))

        for error in extra_errors:
            flash(error, 'danger')
        flash('Veuillez corriger les erreurs dans le formulaire.', 'danger')

    active_questionnaire = Questionnaire.query.filter_by(is_active=True).order_by(Questionnaire.created_at.desc()).first()
    return render_template(
        'survey.html',
        active_questionnaire=active_questionnaire,
        class_questions=class_questions,
        volets=VOLETS,
        volet_labels=VOLET_LABELS,
        questions_by_volet=questions_by_volet,
    )


@app.route('/admin')
def admin():
    if not ensure_admin_session():
        return redirect(url_for('login'))

    ensure_default_classes()
    classes = Classe.query.filter(Classe.nom.in_(CLASS_LEVELS)).order_by(Classe.nom.asc()).all()
    matieres = Matiere.query.all()
    teachers = Teacher.query.order_by(Teacher.created_at.desc()).all()
    questionnaires = Questionnaire.query.order_by(Questionnaire.created_at.desc()).all()
    class_questions = ClassQuestion.query.order_by(ClassQuestion.class_name.asc(), ClassQuestion.created_at.asc()).all()
    campaigns = EvaluationCampaign.query.order_by(EvaluationCampaign.created_at.desc()).all()
    recent_tokens = EvaluationToken.query.order_by(EvaluationToken.created_at.desc()).limit(30).all()
    recent_survey_responses = SurveyResponse.query.order_by(SurveyResponse.id.desc()).limit(50).all()

    return render_template(
        'admin.html',
        classes=classes,
        matieres=matieres,
        teachers=teachers,
        questionnaires=questionnaires,
        class_questions=class_questions,
        filieres=ALL_FILIERES,
        class_levels=CLASS_LEVELS,
        volets=VOLETS,
        volet_labels=VOLET_LABELS,
        campaigns=campaigns,
        recent_tokens=recent_tokens,
        recent_survey_responses=recent_survey_responses,
    )


@app.route('/create_campaign', methods=['POST'])
def create_campaign():
    if not ensure_admin_session():
        return redirect(url_for('login'))

    name = request.form.get('campaign_name', '').strip()
    if not name:
        flash('Nom de campagne invalide.', 'danger')
        return redirect(url_for('admin'))

    campaign = EvaluationCampaign(name=name, filiere_name=CAMPAIGN_GLOBAL_LABEL, is_active=False)
    db.session.add(campaign)
    db.session.commit()
    log_audit('campaign_created', f'name={name}')
    flash('Campagne créée avec succès.', 'success')
    return redirect(url_for('admin'))


@app.route('/activate_campaign/<int:campaign_id>', methods=['POST'])
def activate_campaign(campaign_id):
    if not ensure_admin_session():
        return redirect(url_for('login'))

    campaign = EvaluationCampaign.query.get_or_404(campaign_id)
    EvaluationCampaign.query.filter_by(is_active=True).update({'is_active': False})
    campaign.is_active = True
    db.session.commit()
    log_audit('campaign_activated', f'name={campaign.name}')
    flash(f'Campagne "{campaign.name}" activée.', 'success')
    return redirect(url_for('admin'))



@app.route('/deactivate_campaign/<int:campaign_id>', methods=['POST'])
def deactivate_campaign(campaign_id):
    if not ensure_admin_session():
        return redirect(url_for('login'))

    campaign = EvaluationCampaign.query.get_or_404(campaign_id)
    campaign.is_active = False
    db.session.commit()
    log_audit('campaign_deactivated', f'name={campaign.name}, filiere={campaign.filiere_name}')
    flash(f'Campagne "{campaign.name}" désactivée.', 'success')
    return redirect(url_for('admin'))


@app.route('/delete_campaign/<int:campaign_id>', methods=['POST'])
def delete_campaign(campaign_id):
    if not ensure_admin_session():
        return redirect(url_for('login'))

    campaign = EvaluationCampaign.query.get_or_404(campaign_id)
    deleted_tokens_count = EvaluationToken.query.filter_by(campaign_id=campaign.id).delete()
    campaign_name = campaign.name
    db.session.delete(campaign)
    db.session.commit()
    log_audit('campaign_deleted', f'name={campaign_name}, deleted_tokens={deleted_tokens_count}')
    flash(f'Campagne "{campaign_name}" supprimée.', 'success')
    return redirect(url_for('admin'))


@app.route('/admin/audit', methods=['GET'])
def admin_audit():
    if not ensure_admin_session():
        return redirect(url_for('login'))

    logs = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(300).all()
    return render_template('audit_logs.html', logs=logs)


@app.route('/generate_tokens', methods=['POST'])
def generate_tokens():
    if not ensure_admin_session():
        return redirect(url_for('login'))

    filiere = request.form.get('filiere', '').strip()
    classe_name = request.form.get('classe_name', '').strip()
    subject_name = request.form.get('subject_name', '').strip()
    campaign_id = request.form.get('campaign_id', type=int)
    count = request.form.get('count', type=int)

    normalized_filiere = normalize_filiere_for_class(classe_name, filiere)
    if not normalized_filiere or not classe_name or not subject_name:
        flash('Paramètres de génération invalides.', 'danger')
        return redirect(url_for('admin'))

    if not count or count < 1 or count > 200:
        flash('Le nombre de tokens doit être entre 1 et 200.', 'danger')
        return redirect(url_for('admin'))

    campaign = EvaluationCampaign.query.get(campaign_id) if campaign_id else None
    if not campaign:
        flash('Campagne invalide.', 'danger')
        return redirect(url_for('admin'))

    subject = Matiere.query.filter_by(nom=subject_name, class_name=classe_name).filter(
        Matiere.filiere_name.in_([normalized_filiere, TRONC_COMMUN_LABEL, 'ALL'])
    ).first()
    if not subject:
        flash('La matière sélectionnée ne correspond pas à la classe/filière choisie.', 'danger')
        return redirect(url_for('admin'))

    created = 0
    for _ in range(count):
        db.session.add(EvaluationToken(
            token=generate_unique_token(),
            filiere_name=normalized_filiere,
            class_name=classe_name,
            subject_name=subject_name,
            campaign_id=campaign.id,
            is_used=False,
        ))
        created += 1

    db.session.commit()
    log_audit('tokens_generated', f'count={created}, filiere={normalized_filiere}, classe={classe_name}, matiere={subject_name}')
    flash(f'{created} tokens générés pour {normalized_filiere} / {classe_name} / {subject_name}.', 'success')
    return redirect(url_for('admin'))


@app.route('/change_credentials', methods=['GET', 'POST'])
def change_credentials():
    global ADMIN_USERNAME, ADMIN_PASSWORD_HASH
    if not ensure_admin_session():
        return redirect(url_for('login'))

    if request.method == 'POST':
        old_username = request.form['old_username']
        old_password = request.form['old_password']
        new_username = request.form['new_username']
        new_password = request.form['new_password']

        if old_username == ADMIN_USERNAME and check_password_hash(ADMIN_PASSWORD_HASH, old_password):
            ADMIN_USERNAME = new_username
            ADMIN_PASSWORD_HASH = generate_password_hash(new_password)
            log_audit('admin_credentials_changed', f'new_username={new_username}')
            flash('Nom d\'utilisateur et mot de passe mis à jour avec succès.', 'success')
            return redirect(url_for('admin'))
        flash('L\'ancien nom d\'utilisateur ou mot de passe est incorrect.', 'danger')

    return render_template('change_credentials.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username == ADMIN_USERNAME and check_password_hash(ADMIN_PASSWORD_HASH, password):
            session['admin'] = True
            session['username'] = username
            log_audit('admin_login', f'user={username}')
            flash('Vous êtes connecté.', 'success')
            return redirect(url_for('admin'))
        flash('Nom d\'utilisateur ou mot de passe incorrect.', 'danger')
    return render_template('login.html')


@app.route('/teacher/login', methods=['GET', 'POST'])
def teacher_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        db_teacher = Teacher.query.filter_by(username=username, is_active=True).first()
        is_db_teacher_valid = db_teacher and check_password_hash(db_teacher.password_hash, password)
        is_fallback_teacher_valid = username == TEACHER_USERNAME and check_password_hash(TEACHER_PASSWORD_HASH, password)

        if is_db_teacher_valid or is_fallback_teacher_valid:
            session['teacher'] = True
            session['teacher_username'] = username
            session['teacher_subject_name'] = db_teacher.assigned_subject_name if is_db_teacher_valid else None
            log_audit('teacher_login', f'user={username}')
            flash('Connexion enseignant réussie.', 'success')
            return redirect(url_for('teacher_dashboard'))
        flash('Identifiants enseignant incorrects.', 'danger')
    return render_template('teacher_login.html')


@app.route('/teacher/logout')
def teacher_logout():
    if session.get('teacher'):
        log_audit('teacher_logout', f'user={session.get("teacher_username", "enseignant")}')
    session.pop('teacher', None)
    session.pop('teacher_username', None)
    session.pop('teacher_subject_name', None)
    flash('Vous êtes déconnecté de l\'espace enseignant.', 'success')
    return redirect(url_for('teacher_login'))


@app.route('/teacher/dashboard', methods=['GET'])
def teacher_dashboard():
    if not ensure_teacher_session():
        return redirect(url_for('teacher_login'))

    ensure_default_classes()
    filiere_name = request.args.get('filiere', '').strip() or None
    classe_name = request.args.get('classe', '').strip() or None
    requested_subject_name = request.args.get('matiere', '').strip() or None
    teacher_subject_name = session.get('teacher_subject_name')
    subject_name = teacher_subject_name or requested_subject_name

    responses = build_dashboard_query(filiere_name, classe_name, subject_name).all()
    total = len(responses)
    comments = [r.feedback for r in responses if r.feedback]

    metrics = {
        'total': total,
        'satisfaction': round(sum(r.overall_satisfaction for r in responses) / total, 2) if total else 0,
        'pedagogy': round((
            sum(r.professor_motivation for r in responses)
            + sum(r.tools_methodology for r in responses)
            + sum(r.explanations_clarity for r in responses)
        ) / (3 * total), 2) if total else 0,
        'organization': round(sum(r.schedule_organization for r in responses) / total, 2) if total else 0,
        'infrastructure': round(sum(r.infrastructure_quality for r in responses) / total, 2) if total else 0,
    }

    classes = Classe.query.filter(Classe.nom.in_(CLASS_LEVELS)).order_by(Classe.nom.asc()).all()
    matieres = Matiere.query.all()
    return render_template(
        'teacher_dashboard.html',
        metrics=metrics,
        comments=comments[:30],
        filieres=ALL_FILIERES,
        classes=classes,
        matieres=matieres,
        teacher_subject_name=teacher_subject_name,
        selected={
            'filiere': filiere_name or '',
            'classe': classe_name or '',
            'matiere': subject_name or '',
        },
    )


@app.route('/logout')
def logout():
    if session.get('admin'):
        log_audit('admin_logout', f'user={session.get("username", "admin")}')
    session.pop('admin', None)
    session.pop('username', None)
    flash('Vous avez été déconnecté.', 'success')
    return redirect(url_for('login'))


@app.route('/class_subject', methods=['GET', 'POST'])
def select():
    ensure_default_classes()
    if request.method == 'POST':
        filiere_name = request.form.get('filiere', '').strip()
        classe_id = request.form.get('classe')
        matiere_id = request.form.get('matiere')
        access_token = request.form.get('access_token', '').strip().upper()

        if classe_id and matiere_id and access_token:
            classe = Classe.query.get(classe_id)
            matiere = Matiere.query.get(matiere_id)
            if not classe or not matiere:
                flash('Classe ou matière invalide.', 'danger')
                return redirect(url_for('select'))

            normalized_filiere = normalize_filiere_for_class(classe.nom, filiere_name)
            if not normalized_filiere:
                flash('Veuillez sélectionner une filière valide pour cette classe.', 'danger')
                return redirect(url_for('select'))

            if matiere.class_name not in ('ALL', classe.nom):
                flash('La matière ne correspond pas à la classe sélectionnée.', 'danger')
                return redirect(url_for('select'))

            if matiere.filiere_name not in ('ALL', normalized_filiere, TRONC_COMMUN_LABEL):
                flash('La matière ne correspond pas à la filière sélectionnée.', 'danger')
                return redirect(url_for('select'))

            token_obj = EvaluationToken.query.filter_by(
                token=access_token,
                filiere_name=normalized_filiere,
                class_name=classe.nom,
                subject_name=matiere.nom,
                is_used=False,
            ).first()

            if not token_obj:
                flash('Token invalide pour cette filière/classe/matière ou déjà utilisé.', 'danger')
                return redirect(url_for('select'))

            campaign = EvaluationCampaign.query.get(token_obj.campaign_id) if token_obj.campaign_id else None
            if not campaign or not campaign.is_active:
                flash('La campagne associée au token est fermée.', 'danger')
                return redirect(url_for('select'))

            session['filiere_name'] = normalized_filiere
            session['class_name'] = classe.nom
            session['subject_name'] = matiere.nom
            session['token_id'] = token_obj.id
            log_audit('token_validated', f'token={access_token}, filiere={normalized_filiere}, classe={classe.nom}, matiere={matiere.nom}')
            return redirect(url_for('survey'))

        flash('Veuillez sélectionner une classe, une matière et saisir un token.', 'danger')

    classes = Classe.query.filter(Classe.nom.in_(CLASS_LEVELS)).order_by(Classe.nom.asc()).all()
    matieres = Matiere.query.order_by(Matiere.nom.asc()).all()
    return render_template('class_subject.html', classes=classes, matieres=matieres, filieres=ALL_FILIERES)


@app.route('/result')
def result():
    return render_template('result.html')


@app.route('/report', methods=['GET', 'POST'])
def generate_report():
    classe_name = request.form.get('classe', '').strip()
    matiere_name = request.form.get('matiere', '').strip()
    filiere_name = normalize_filiere_for_class(classe_name, request.form.get('filiere', '').strip())

    if not classe_name or not matiere_name or not filiere_name:
        flash('Veuillez sélectionner une classe, une filière valide et une matière.', 'warning')
        return redirect(url_for('admin'))

    responses = SurveyResponse.query.filter_by(
        filiere_name=filiere_name,
        class_name=classe_name,
        subject_name=matiere_name
    ).all()

    if not responses:
        flash('Aucune donnée trouvée pour cette filière, classe et matière.', 'warning')
        return redirect(url_for('admin'))

    avg_involvement = sum(resp.involvement for resp in responses) / len(responses)
    avg_initial_knowledge = sum(resp.initial_knowledge for resp in responses) / len(responses)
    avg_current_knowledge = sum(resp.current_knowledge for resp in responses) / len(responses)
    avg_professor_motivation = sum(resp.professor_motivation for resp in responses) / len(responses)
    avg_tools_methodology = sum(resp.tools_methodology for resp in responses) / len(responses)
    avg_examples_exercises = sum(resp.examples_exercises for resp in responses) / len(responses)
    avg_explanations_clarity = sum(resp.explanations_clarity for resp in responses) / len(responses)
    avg_satisfaction_general = sum(resp.overall_satisfaction for resp in responses) / len(responses)
    avg_schedule_organization = sum(resp.schedule_organization for resp in responses) / len(responses)
    avg_infrastructure_quality = sum(resp.infrastructure_quality for resp in responses) / len(responses)
    practical_skills_yes = sum(1 for resp in responses if resp.practical_skills == 'oui')
    course_organization_yes = sum(1 for resp in responses if resp.course_organization == 'oui')

    return render_template(
        'report.html',
        classe_name=classe_name,
        filiere_name=filiere_name,
        matiere_name=matiere_name,
        avg_involvement=avg_involvement,
        avg_initial_knowledge=avg_initial_knowledge,
        avg_current_knowledge=avg_current_knowledge,
        avg_professor_motivation=avg_professor_motivation,
        avg_tools_methodology=avg_tools_methodology,
        avg_examples_exercises=avg_examples_exercises,
        avg_explanations_clarity=avg_explanations_clarity,
        avg_satisfaction_general=avg_satisfaction_general,
        avg_schedule_organization=avg_schedule_organization,
        avg_infrastructure_quality=avg_infrastructure_quality,
        practical_skills_yes=practical_skills_yes,
        course_organization_yes=course_organization_yes,
        responses_len=len(responses),
    )


@app.route('/dashboard', methods=['GET'])
def dashboard():
    if not ensure_admin_session():
        return redirect(url_for('login'))

    filiere_name = request.args.get('filiere', '').strip()
    classe_name = request.args.get('classe', '').strip()
    subject_name = request.args.get('matiere', '').strip()

    query = build_dashboard_query(
        filiere_name=filiere_name or None,
        classe_name=classe_name or None,
        subject_name=subject_name or None,
    )
    responses = query.all()

    total = len(responses)
    if total == 0:
        metrics = {
            'participation': 0,
            'satisfaction': 0,
            'organization': 0,
            'infrastructure': 0,
            'pedagogy': 0,
        }
    else:
        metrics = {
            'participation': total,
            'satisfaction': round(sum(r.overall_satisfaction for r in responses) / total, 2),
            'organization': round(sum(r.schedule_organization for r in responses) / total, 2),
            'infrastructure': round(sum(r.infrastructure_quality for r in responses) / total, 2),
            'pedagogy': round((
                sum(r.professor_motivation for r in responses)
                + sum(r.tools_methodology for r in responses)
                + sum(r.explanations_clarity for r in responses)
            ) / (3 * total), 2),
        }

    classes = Classe.query.all()
    matieres = Matiere.query.all()
    return render_template(
        'dashboard.html',
        metrics=metrics,
        filieres=ALL_FILIERES,
        classes=classes,
        matieres=matieres,
        selected={
            'filiere': filiere_name,
            'classe': classe_name,
            'matiere': subject_name,
        },
    )


@app.route('/dashboard/export.csv', methods=['GET'])
def dashboard_export_csv():
    if not ensure_admin_session():
        return redirect(url_for('login'))

    filiere_name = request.args.get('filiere', '').strip() or None
    classe_name = request.args.get('classe', '').strip() or None
    subject_name = request.args.get('matiere', '').strip() or None

    responses = build_dashboard_query(filiere_name, classe_name, subject_name).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        'filiere', 'classe', 'matiere', 'satisfaction_generale', 'organisation',
        'infrastructures', 'motivation_prof', 'methodologie', 'clarte', 'feedback'
    ])
    for r in responses:
        writer.writerow([
            r.filiere_name,
            r.class_name,
            r.subject_name,
            r.overall_satisfaction,
            r.schedule_organization,
            r.infrastructure_quality,
            r.professor_motivation,
            r.tools_methodology,
            r.explanations_clarity,
            r.feedback or '',
        ])

    csv_data = output.getvalue()
    filename = f"dashboard_export_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        csv_data,
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename={filename}'},
    )


@app.route('/reset_survey_responses', methods=['POST'])
def reset_survey_responses():
    if not ensure_admin_session():
        return redirect(url_for('login'))

    try:
        db.session.query(SurveyResponse).delete()
        db.session.commit()
        log_audit('responses_reset', 'all survey responses deleted by admin')
        flash('Tous les résultats ont été réinitialisés avec succès.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Erreur lors de la réinitialisation des résultats : {e}', 'danger')

    return redirect(url_for('admin'))


@app.route('/delete_survey_response/<int:response_id>', methods=['POST'])
def delete_survey_response(response_id):
    if not ensure_admin_session():
        return redirect(url_for('login'))

    response = SurveyResponse.query.get_or_404(response_id)
    ClassQuestionAnswer.query.filter_by(survey_response_id=response.id).delete()
    db.session.delete(response)
    db.session.commit()
    log_audit('survey_response_deleted', f'response_id={response_id}')
    flash('Sondage supprimé avec succès.', 'success')
    return redirect(url_for('admin'))


@app.route('/show_table', methods=['GET'])
def show_table():
    class_name = request.args.get('class_name', None)
    filiere_name = request.args.get('filiere_name', None)

    if class_name and filiere_name:
        survey_responses = SurveyResponse.query.filter_by(class_name=class_name, filiere_name=filiere_name).all()
    elif class_name:
        survey_responses = SurveyResponse.query.filter_by(class_name=class_name).all()
    elif filiere_name:
        survey_responses = SurveyResponse.query.filter_by(filiere_name=filiere_name).all()
    else:
        survey_responses = SurveyResponse.query.all()

    return render_template('show_table.html', survey_responses=survey_responses)


@app.route('/add_matiere', methods=['POST'])
def add_matiere():
    if not ensure_admin_session():
        return redirect(url_for('login'))

    matiere_name = request.form.get('matiere_name', '').strip()
    class_name = request.form.get('class_name', '').strip()
    filiere_name = request.form.get('filiere_name', '').strip()

    if matiere_name and class_name:
        if class_name not in CLASS_LEVELS:
            flash('Veuillez sélectionner une classe valide (L1/L2/L3).', 'danger')
            return redirect(url_for('admin'))

        normalized_filiere = normalize_filiere_for_class(class_name, filiere_name)
        if not normalized_filiere:
            flash('Veuillez sélectionner une filière valide pour cette classe.', 'danger')
            return redirect(url_for('admin'))

        existing = Matiere.query.filter_by(
            nom=matiere_name,
            class_name=class_name,
            filiere_name=normalized_filiere,
        ).first()
        if existing:
            flash('Cette matière existe déjà pour cette classe/filière.', 'warning')
            return redirect(url_for('admin'))

        db.session.add(Matiere(nom=matiere_name, class_name=class_name, filiere_name=normalized_filiere))
        db.session.commit()
        log_audit('matiere_added', f'nom={matiere_name}, classe={class_name}, filiere={normalized_filiere}')
        flash('Matière ajoutée avec succès.', 'success')
    else:
        flash('Le nom de la matière et la classe sont requis.', 'danger')
    return redirect(url_for('admin'))


@app.route('/delete_matiere', methods=['POST'])
def delete_matiere():
    if not ensure_admin_session():
        return redirect(url_for('login'))

    matiere_id = request.form.get('matiere_id')
    if matiere_id:
        matiere_to_delete = Matiere.query.get(matiere_id)
        if matiere_to_delete:
            db.session.delete(matiere_to_delete)
            db.session.commit()
            log_audit(
                'matiere_deleted',
                f'nom={matiere_to_delete.nom}, classe={matiere_to_delete.class_name}, filiere={matiere_to_delete.filiere_name}'
            )
            flash('Matière supprimée avec succès.', 'success')
    return redirect(url_for('admin'))


@app.route('/add_classe', methods=['POST'])
def add_classe():
    if not ensure_admin_session():
        return redirect(url_for('login'))

    classe_name = request.form.get('classe_name')
    if classe_name:
        db.session.add(Classe(nom=classe_name))
        db.session.commit()
        log_audit('classe_added', f'nom={classe_name}')
        flash('Classe ajoutée avec succès.', 'success')
    return redirect(url_for('admin'))


@app.route('/delete_classe', methods=['POST'])
def delete_classe():
    if not ensure_admin_session():
        return redirect(url_for('login'))

    classe_id = request.form.get('classe_id')
    if classe_id:
        classe_to_delete = Classe.query.get(classe_id)
        if classe_to_delete:
            db.session.delete(classe_to_delete)
            db.session.commit()
            log_audit('classe_deleted', f'nom={classe_to_delete.nom}')
            flash('Classe supprimée avec succès.', 'success')
    return redirect(url_for('admin'))


@app.route('/add_teacher', methods=['POST'])
def add_teacher():
    if not ensure_admin_session():
        return redirect(url_for('login'))

    username = request.form.get('teacher_username', '').strip()
    password = request.form.get('teacher_password', '').strip()
    full_name = request.form.get('teacher_full_name', '').strip()
    assigned_subject_name = request.form.get('teacher_subject_name', '').strip()

    if not username or not password:
        flash('Nom d\'utilisateur et mot de passe enseignant requis.', 'danger')
        return redirect(url_for('admin'))

    existing = Teacher.query.filter_by(username=username).first()
    if existing:
        flash('Ce nom d\'utilisateur enseignant existe déjà.', 'warning')
        return redirect(url_for('admin'))

    if assigned_subject_name and not Matiere.query.filter_by(nom=assigned_subject_name).first():
        flash('La matière associée à l\'enseignant est invalide.', 'danger')
        return redirect(url_for('admin'))

    teacher = Teacher(
        username=username,
        password_hash=generate_password_hash(password),
        full_name=full_name or None,
        assigned_subject_name=assigned_subject_name or None,
        is_active=True,
    )
    db.session.add(teacher)
    db.session.commit()
    log_audit('teacher_added', f'username={username}, full_name={full_name}, subject={assigned_subject_name or "ALL"}')
    flash('Enseignant ajouté avec succès.', 'success')
    return redirect(url_for('admin'))


@app.route('/toggle_teacher_status', methods=['POST'])
def toggle_teacher_status():
    if not ensure_admin_session():
        return redirect(url_for('login'))

    teacher_id = request.form.get('teacher_id', type=int)
    teacher = Teacher.query.get(teacher_id)
    if not teacher:
        flash('Enseignant introuvable.', 'danger')
        return redirect(url_for('admin'))

    teacher.is_active = not teacher.is_active
    db.session.commit()
    log_audit('teacher_status_changed', f'username={teacher.username}, is_active={teacher.is_active}')
    flash('Statut enseignant mis à jour.', 'success')
    return redirect(url_for('admin'))


@app.route('/add_class_question', methods=['POST'])
def add_class_question():
    if not ensure_admin_session():
        return redirect(url_for('login'))

    class_name = request.form.get('class_name', '').strip()
    filiere_name = request.form.get('filiere_name', '').strip()
    volet_name = request.form.get('volet_name', 'enseignement').strip()
    question_text = request.form.get('question_text', '').strip()
    response_type = request.form.get('response_type', 'scale').strip()

    normalized_filiere = normalize_filiere_for_class(class_name, filiere_name)
    if not normalized_filiere:
        flash('Veuillez sélectionner une filière valide pour cette classe.', 'danger')
        return redirect(url_for('admin'))

    if not class_name or volet_name not in VOLETS or not question_text or response_type not in {'scale', 'text'}:
        flash('Paramètres invalides pour la question de classe.', 'danger')
        return redirect(url_for('admin'))

    db.session.add(ClassQuestion(
        class_name=class_name,
        filiere_name=normalized_filiere,
        volet_name=volet_name,
        question_text=question_text,
        response_type=response_type,
    ))
    db.session.commit()
    log_audit('class_question_added', f'class={class_name}, filiere={normalized_filiere}, volet={volet_name}, response_type={response_type}, question={question_text[:80]}')
    flash('Question de classe ajoutée avec succès.', 'success')
    return redirect(url_for('admin'))


@app.route('/delete_class_question', methods=['POST'])
def delete_class_question():
    if not ensure_admin_session():
        return redirect(url_for('login'))

    question_id = request.form.get('question_id', type=int)
    question = ClassQuestion.query.get(question_id)
    if not question:
        flash('Question de classe introuvable.', 'danger')
        return redirect(url_for('admin'))

    db.session.delete(question)
    db.session.commit()
    log_audit('class_question_deleted', f'id={question_id}, class={question.class_name}')
    flash('Question de classe supprimée.', 'success')
    return redirect(url_for('admin'))


@app.route('/add_questionnaire', methods=['POST'])
def add_questionnaire():
    if not ensure_admin_session():
        return redirect(url_for('login'))

    title = request.form.get('questionnaire_title', '').strip()
    description = request.form.get('questionnaire_description', '').strip()
    is_active = bool(request.form.get('questionnaire_active'))

    if not title:
        flash('Le titre du questionnaire est obligatoire.', 'danger')
        return redirect(url_for('admin'))

    q = Questionnaire(title=title, description=description or None, is_active=is_active)
    db.session.add(q)
    db.session.commit()
    log_audit('questionnaire_added', f'title={title}, active={is_active}')
    flash('Questionnaire ajouté avec succès.', 'success')
    return redirect(url_for('admin'))


@app.route('/edit_questionnaire/<int:questionnaire_id>', methods=['GET', 'POST'])
def edit_questionnaire(questionnaire_id):
    if not ensure_admin_session():
        return redirect(url_for('login'))

    questionnaire = Questionnaire.query.get_or_404(questionnaire_id)

    if request.method == 'POST':
        title = request.form.get('questionnaire_title', '').strip()
        description = request.form.get('questionnaire_description', '').strip()
        is_active = bool(request.form.get('questionnaire_active'))

        if not title:
            flash('Le titre du questionnaire est obligatoire.', 'danger')
            return redirect(url_for('edit_questionnaire', questionnaire_id=questionnaire_id))

        questionnaire.title = title
        questionnaire.description = description or None
        questionnaire.is_active = is_active
        db.session.commit()
        log_audit('questionnaire_updated', f'id={questionnaire_id}, title={title}, active={is_active}')
        flash('Questionnaire modifié avec succès.', 'success')
        return redirect(url_for('admin'))

    return render_template('edit_questionnaire.html', questionnaire=questionnaire)


@app.route('/delete_questionnaire', methods=['POST'])
def delete_questionnaire():
    if not ensure_admin_session():
        return redirect(url_for('login'))

    questionnaire_id = request.form.get('questionnaire_id', type=int)
    questionnaire = Questionnaire.query.get(questionnaire_id)
    if not questionnaire:
        flash('Questionnaire introuvable.', 'danger')
        return redirect(url_for('admin'))

    title = questionnaire.title
    db.session.delete(questionnaire)
    db.session.commit()
    log_audit('questionnaire_deleted', f'id={questionnaire_id}, title={title}')
    flash('Questionnaire supprimé avec succès.', 'success')
    return redirect(url_for('admin'))


def run_schema_updates():
    """Mise à jour légère du schéma SQLite pour les installations existantes."""
    result = db.session.execute(text("PRAGMA table_info(survey_response)"))
    columns = {row[1] for row in result}
    if 'filiere_name' not in columns:
        db.session.execute(text("ALTER TABLE survey_response ADD COLUMN filiere_name VARCHAR(20) DEFAULT 'I'"))
        db.session.execute(text("UPDATE survey_response SET filiere_name = 'I' WHERE filiere_name IS NULL"))
        db.session.commit()

    if 'schedule_organization' not in columns:
        db.session.execute(text("ALTER TABLE survey_response ADD COLUMN schedule_organization INTEGER DEFAULT 0"))
        db.session.execute(text("UPDATE survey_response SET schedule_organization = 0 WHERE schedule_organization IS NULL"))
        db.session.commit()

    if 'infrastructure_quality' not in columns:
        db.session.execute(text("ALTER TABLE survey_response ADD COLUMN infrastructure_quality INTEGER DEFAULT 0"))
        db.session.execute(text("UPDATE survey_response SET infrastructure_quality = 0 WHERE infrastructure_quality IS NULL"))
        db.session.commit()

    teacher_columns = {row[1] for row in db.session.execute(text("PRAGMA table_info(teacher)"))}
    if 'assigned_subject_name' not in teacher_columns:
        db.session.execute(text("ALTER TABLE teacher ADD COLUMN assigned_subject_name VARCHAR(100)"))
        db.session.commit()

    class_question_columns = {row[1] for row in db.session.execute(text("PRAGMA table_info(class_question)"))}
    if 'filiere_name' not in class_question_columns:
        db.session.execute(text("ALTER TABLE class_question ADD COLUMN filiere_name VARCHAR(30) DEFAULT 'ALL'"))
        db.session.execute(text("UPDATE class_question SET filiere_name = 'ALL' WHERE filiere_name IS NULL"))
        db.session.commit()

    class_question_columns = {row[1] for row in db.session.execute(text("PRAGMA table_info(class_question)"))}
    if 'volet_name' not in class_question_columns:
        db.session.execute(text("ALTER TABLE class_question ADD COLUMN volet_name VARCHAR(30) DEFAULT 'enseignement'"))
        db.session.execute(text("UPDATE class_question SET volet_name = 'enseignement' WHERE volet_name IS NULL"))
        db.session.commit()

    matiere_columns = {row[1] for row in db.session.execute(text("PRAGMA table_info(matiere)"))}
    if 'class_name' not in matiere_columns:
        db.session.execute(text("ALTER TABLE matiere ADD COLUMN class_name VARCHAR(100) DEFAULT 'ALL'"))
        db.session.execute(text("UPDATE matiere SET class_name = 'ALL' WHERE class_name IS NULL"))
        db.session.commit()

    matiere_columns = {row[1] for row in db.session.execute(text("PRAGMA table_info(matiere)"))}
    if 'filiere_name' not in matiere_columns:
        db.session.execute(text("ALTER TABLE matiere ADD COLUMN filiere_name VARCHAR(30) DEFAULT 'ALL'"))
        db.session.execute(text("UPDATE matiere SET filiere_name = 'ALL' WHERE filiere_name IS NULL"))
        db.session.commit()


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        run_schema_updates()
        ensure_default_classes()
        app.run(host='0.0.0.0', port=5000)
