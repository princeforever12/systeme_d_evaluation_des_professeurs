from datetime import datetime
import secrets
import string
import csv
import io
import os

from flask import Flask, render_template, request, redirect, url_for, session, flash, Response, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import FlaskForm
from sqlalchemy import text
from wtforms import RadioField, SelectField, TextAreaField, SubmitField
from wtforms.validators import DataRequired
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'dev-secret-key-change-me')

# Configuration de la base de données
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

FILIERES_ITER = ['I', 'IMT', 'EEA']


# Modèles de base de données
class Classe(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(100), nullable=False)


class Matiere(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(100), nullable=False)


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


class SurveyForm(FlaskForm):
    involvement = RadioField(
        'Quel est votre niveau d\'implication dans le cours ?',
        choices=[(str(i), str(i)) for i in range(11)],
        validators=[DataRequired()]
    )
    initial_knowledge = RadioField(
        'Quel était votre niveau de compétences/connaissances en début ?',
        choices=[(str(i), str(i)) for i in range(11)],
        validators=[DataRequired()]
    )
    current_knowledge = RadioField(
        'Quel est votre niveau de compétences/connaissances actuel ?',
        choices=[(str(i), str(i)) for i in range(11)],
        validators=[DataRequired()]
    )
    professor_motivation = RadioField(
        'Comment évaluez-vous la motivation et les échanges avec le professeur ?',
        choices=[(str(i), str(i)) for i in range(11)],
        validators=[DataRequired()]
    )
    tools_methodology = RadioField(
        'Comment trouvez-vous les outils et méthodologies développés par le professeur ?',
        choices=[(str(i), str(i)) for i in range(11)],
        validators=[DataRequired()]
    )
    examples_exercises = RadioField(
        'Veuillez noter les exemples employés et les exercices réalisés',
        choices=[(str(i), str(i)) for i in range(11)],
        validators=[DataRequired()]
    )
    explanations_clarity = RadioField(
        'Veuillez noter la pertinence et la clarté des explications',
        choices=[(str(i), str(i)) for i in range(11)],
        validators=[DataRequired()]
    )
    practical_skills = SelectField(
        'Pensez-vous être capable de mettre en pratique les acquisitions ?',
        choices=[('oui', 'Oui'), ('non', 'Non')],
        validators=[DataRequired()]
    )
    course_organization = SelectField(
        'Êtes-vous satisfait(e) des conditions d\'organisation du cours (salle, installation, matériels, etc.) ?',
        choices=[('oui', 'Oui'), ('non', 'Non')],
        validators=[DataRequired()]
    )
    schedule_organization = RadioField(
        'Comment évaluez-vous l\'organisation (emploi du temps, coordination, communication) ?',
        choices=[(str(i), str(i)) for i in range(11)],
        validators=[DataRequired()]
    )
    infrastructure_quality = RadioField(
        'Comment évaluez-vous les infrastructures pédagogiques (salles, équipements, réseau, plateformes) ?',
        choices=[(str(i), str(i)) for i in range(11)],
        validators=[DataRequired()]
    )
    overall_satisfaction = RadioField(
        'Quel est votre niveau de satisfaction générale ?',
        choices=[(str(i), str(i)) for i in range(11)],
        validators=[DataRequired()]
    )
    feedback = TextAreaField('Commentaires supplémentaires')
    submit = SubmitField('Soumettre')


# Stockage sécurisé des mots de passe
ADMIN_USERNAME = os.getenv('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD_HASH = generate_password_hash(os.getenv('ADMIN_PASSWORD', 'adminpassword'))


def ensure_admin_session():
    if not session.get('admin'):
        flash('Veuillez vous connecter pour accéder à cette page.', 'danger')
        return False
    return True


def log_audit(action, details=''):
    actor = session.get('username', 'anonymous')
    db.session.add(AuditLog(actor=actor, action=action, details=details[:500]))
    db.session.commit()


def generate_unique_token():
    alphabet = string.ascii_uppercase + string.digits
    while True:
        token = ''.join(secrets.choice(alphabet) for _ in range(10))
        if not EvaluationToken.query.filter_by(token=token).first():
            return token


def build_dashboard_query(filiere_name=None, classe_name=None, subject_name=None):
    query = SurveyResponse.query
    if filiere_name:
        query = query.filter_by(filiere_name=filiere_name)
    if classe_name:
        query = query.filter_by(class_name=classe_name)
    if subject_name:
        query = query.filter_by(subject_name=subject_name)
    return query



def ensure_admin_session():
    if not session.get('admin'):
        flash('Veuillez vous connecter pour accéder à cette page.', 'danger')
        return False
    return True


def generate_unique_token():
    alphabet = string.ascii_uppercase + string.digits
    while True:
        token = ''.join(secrets.choice(alphabet) for _ in range(10))
        if not EvaluationToken.query.filter_by(token=token).first():
            return token


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
        flash('Veuillez d\'abord sélectionner filière/classe/matière et fournir un token valide.', 'warning')
        return redirect(url_for('select'))

    token_obj = EvaluationToken.query.get(token_id)
    if not token_obj or token_obj.is_used:
        flash('Token invalide ou déjà utilisé.', 'danger')
        return redirect(url_for('select'))

    form = SurveyForm()
    if request.method == 'POST':
        if form.validate():
            new_response = SurveyResponse(
                filiere_name=filiere_name,
                class_name=class_name,
                subject_name=subject_name,
                involvement=int(form.involvement.data),
                initial_knowledge=int(form.initial_knowledge.data),
                current_knowledge=int(form.current_knowledge.data),
                professor_motivation=int(form.professor_motivation.data),
                tools_methodology=int(form.tools_methodology.data),
                examples_exercises=int(form.examples_exercises.data),
                explanations_clarity=int(form.explanations_clarity.data),
                practical_skills=form.practical_skills.data,
                course_organization=form.course_organization.data,
                schedule_organization=int(form.schedule_organization.data),
                infrastructure_quality=int(form.infrastructure_quality.data),
                overall_satisfaction=int(form.overall_satisfaction.data),
                feedback=form.feedback.data
            )
            token_obj.is_used = True
            token_obj.used_at = datetime.utcnow()
            db.session.add(new_response)
            db.session.commit()
            log_audit('survey_submitted', f'filiere={filiere_name}, classe={class_name}, matiere={subject_name}')
            session.pop('token_id', None)
            return redirect(url_for('result'))

        flash('Veuillez corriger les erreurs dans le formulaire.', 'danger')

    return render_template('survey.html', form=form)


@app.route('/admin')
def admin():
    if not ensure_admin_session():
        return redirect(url_for('login'))

    classes = Classe.query.all()
    matieres = Matiere.query.all()
    campaigns = EvaluationCampaign.query.order_by(EvaluationCampaign.created_at.desc()).all()
    recent_tokens = EvaluationToken.query.order_by(EvaluationToken.created_at.desc()).limit(30).all()

    return render_template(
        'admin.html',
        classes=classes,
        matieres=matieres,
        filieres=FILIERES_ITER,
        campaigns=campaigns,
        recent_tokens=recent_tokens,
    )


@app.route('/create_campaign', methods=['POST'])
def create_campaign():
    if not ensure_admin_session():
        return redirect(url_for('login'))

    name = request.form.get('campaign_name', '').strip()
    filiere = request.form.get('filiere', '').strip()
    if not name or filiere not in FILIERES_ITER:
        flash('Nom de campagne ou filière invalide.', 'danger')
        return redirect(url_for('admin'))

    campaign = EvaluationCampaign(name=name, filiere_name=filiere, is_active=False)
    db.session.add(campaign)
    db.session.commit()
    log_audit('campaign_created', f'name={name}, filiere={filiere}')
    flash('Campagne créée avec succès.', 'success')
    return redirect(url_for('admin'))


@app.route('/activate_campaign/<int:campaign_id>', methods=['POST'])
def activate_campaign(campaign_id):
    if not ensure_admin_session():
        return redirect(url_for('login'))

    campaign = EvaluationCampaign.query.get_or_404(campaign_id)
    EvaluationCampaign.query.filter_by(filiere_name=campaign.filiere_name, is_active=True).update({'is_active': False})
    campaign.is_active = True
    db.session.commit()
    log_audit('campaign_activated', f'name={campaign.name}, filiere={campaign.filiere_name}')
    flash(f'Campagne "{campaign.name}" activée pour la filière {campaign.filiere_name}.', 'success')
    return redirect(url_for('admin'))


@app.route('/generate_tokens', methods=['POST'])
def generate_tokens():
    if not ensure_admin_session():
        return redirect(url_for('login'))

    filiere = request.form.get('filiere', '').strip()
    classe_name = request.form.get('classe_name', '').strip()
    subject_name = request.form.get('subject_name', '').strip()
    campaign_id = request.form.get('campaign_id', type=int)
    count = request.form.get('count', type=int)

    if filiere not in FILIERES_ITER or not classe_name or not subject_name:
        flash('Paramètres de génération invalides.', 'danger')
        return redirect(url_for('admin'))

    if not count or count < 1 or count > 200:
        flash('Le nombre de tokens doit être entre 1 et 200.', 'danger')
        return redirect(url_for('admin'))

    campaign = EvaluationCampaign.query.get(campaign_id) if campaign_id else None
    if not campaign or campaign.filiere_name != filiere:
        flash('Campagne invalide pour la filière sélectionnée.', 'danger')
        return redirect(url_for('admin'))

    created = 0
    for _ in range(count):
        db.session.add(EvaluationToken(
            token=generate_unique_token(),
            filiere_name=filiere,
            class_name=classe_name,
            subject_name=subject_name,
            campaign_id=campaign.id,
            is_used=False,
        ))
        created += 1

    db.session.commit()
    log_audit('tokens_generated', f'count={created}, filiere={filiere}, classe={classe_name}, matiere={subject_name}')
    flash(f'{created} tokens générés pour {filiere} / {classe_name} / {subject_name}.', 'success')
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
    if request.method == 'POST':
        filiere_name = request.form.get('filiere')
        classe_id = request.form.get('classe')
        matiere_id = request.form.get('matiere')
        access_token = request.form.get('access_token', '').strip().upper()

        if filiere_name and classe_id and matiere_id and access_token:
            classe = Classe.query.get(classe_id)
            matiere = Matiere.query.get(matiere_id)
            if not classe or not matiere:
                flash('Classe ou matière invalide.', 'danger')
                return redirect(url_for('select'))

            token_obj = EvaluationToken.query.filter_by(
                token=access_token,
                filiere_name=filiere_name,
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

            session['filiere_name'] = filiere_name
            session['class_name'] = classe.nom
            session['subject_name'] = matiere.nom
            session['token_id'] = token_obj.id
            log_audit('token_validated', f'token={access_token}, filiere={filiere_name}, classe={classe.nom}, matiere={matiere.nom}')
            return redirect(url_for('survey'))

        flash('Veuillez sélectionner une filière, une classe, une matière et saisir un token.', 'danger')

    classes = Classe.query.all()
    matieres = Matiere.query.all()
    return render_template('class_subject.html', classes=classes, matieres=matieres, filieres=FILIERES_ITER)


@app.route('/result')
def result():
    return render_template('result.html')


@app.route('/report', methods=['GET', 'POST'])
def generate_report():
    filiere_name = request.form.get('filiere')
    classe_name = request.form.get('classe')
    matiere_name = request.form.get('matiere')

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
        filieres=FILIERES_ITER,
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

    matiere_name = request.form.get('matiere_name')
    if matiere_name:
        db.session.add(Matiere(nom=matiere_name))
        db.session.commit()
        log_audit('matiere_added', f'nom={matiere_name}')
        flash('Matière ajoutée avec succès.', 'success')
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
            log_audit('matiere_deleted', f'nom={matiere_to_delete.nom}')
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


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        run_schema_updates()
        app.run(host='0.0.0.0', port=5000)
