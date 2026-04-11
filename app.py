from datetime import datetime
import secrets
import string
import csv
import io
import os
import re
import unicodedata

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

DEFAULT_QUESTION_BANK = {
    'enseignement': [
        ('Le contenu du cours est-il clair ?', 'scale'),
        ('Les objectifs sont-ils bien définis ?', 'scale'),
        ('Le niveau est-il adapté ?', 'scale'),
        ('Les supports sont-ils de qualité ?', 'scale'),
        ('Le cours favorise-t-il la compréhension ?', 'scale'),
        ('Les exemples sont-ils pertinents ?', 'scale'),
        ('Le contenu est-il à jour ?', 'scale'),
        ('Le volume horaire est-il suffisant ?', 'scale'),
        ('Quelles compétences utiles avez-vous le plus développées dans ce cours ?', 'text'),
        ('Quelle amélioration proposeriez-vous pour ce cours ?', 'text'),
    ],
    'enseignant': [
        ('Maîtrise-t-il son sujet ?', 'scale'),
        ('Explique-t-il clairement ?', 'scale'),
        ('Est-il disponible ?', 'scale'),
        ('Encourage-t-il la participation ?', 'scale'),
        ('Respecte-t-il les horaires ?', 'scale'),
        ('Les méthodes sont-elles adaptées ?', 'scale'),
        ('Donne-t-il des exemples pertinents ?', 'scale'),
        ('Est-il organisé ?', 'scale'),
        ('Quels sont les points forts de l’enseignant ?', 'text'),
        ('Quelles améliorations suggérez-vous pour l’enseignant ?', 'text'),
    ],
    'organisation': [
        ('Emploi du temps organisé ?', 'scale'),
        ('Cours à l’heure ?', 'scale'),
        ('Pas de chevauchement ?', 'scale'),
        ('Informations bien communiquées ?', 'scale'),
        ('Examens bien planifiés ?', 'scale'),
        ('Charge de travail équilibrée ?', 'scale'),
        ('Changements annoncés à temps ?', 'scale'),
        ('Bonne répartition des séances ?', 'scale'),
        ('Quels problèmes d’organisation avez-vous rencontrés ?', 'text'),
        ('Quelle solution proposez-vous pour améliorer l’organisation ?', 'text'),
    ],
    'infrastructures': [
        ('Salles adaptées ?', 'scale'),
        ('Équipements fonctionnels ?', 'scale'),
        ('Internet fiable ?', 'scale'),
        ('Laboratoires équipés ?', 'scale'),
        ('Bibliothèque suffisante ?', 'scale'),
        ('Espaces de travail disponibles ?', 'scale'),
        ('Propreté satisfaisante ?', 'scale'),
        ('Capacité des salles suffisante ?', 'scale'),
        ('Quel équipement/infrastructure manque le plus ?', 'text'),
        ('Quelle priorité d’amélioration recommandez-vous ?', 'text'),
    ],
}
PDF_LOGO_CANDIDATES = [
    os.getenv('SCHOOL_LOGO_PATH', '').strip(),
    os.path.join('static', 'assets', 'utt_loko_logo.jpg'),
    os.path.join('static', 'assets', 'ecole_logo.jpg'),
    os.path.join('static', 'assets', 'logo.jpg'),
]


def get_pdf_logo_path():
    for candidate in PDF_LOGO_CANDIDATES:
        if candidate and os.path.exists(candidate):
            return candidate
    return None


def _pdf_escape(text_value):
    value = unicodedata.normalize('NFKD', str(text_value or '')).encode('ascii', 'ignore').decode('ascii')
    return value.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')


def _get_jpeg_size(data):
    if len(data) < 4 or data[0:2] != b'\xff\xd8':
        return None
    i = 2
    while i < len(data) - 1:
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        i += 2
        if marker in (0xD8, 0xD9):
            continue
        if i + 2 > len(data):
            break
        segment_length = int.from_bytes(data[i:i + 2], 'big')
        if segment_length < 2 or i + segment_length > len(data):
            break
        if marker in (0xC0, 0xC1, 0xC2, 0xC3):
            if i + 7 > len(data):
                break
            height = int.from_bytes(data[i + 3:i + 5], 'big')
            width = int.from_bytes(data[i + 5:i + 7], 'big')
            return width, height
        i += segment_length
    return None


def _compute_table_widths(headers, rows, min_width=8, max_width=34):
    column_count = max(1, len(headers))
    widths = [min(max(len(_pdf_escape(header)) + 2, min_width), max_width) for header in headers]
    for row in rows:
        for idx in range(column_count):
            cell = _pdf_escape(row[idx] if idx < len(row) else '')
            widths[idx] = min(max(widths[idx], len(cell) + 2), max_width)
    return widths


def build_table_pdf(title, headers, rows, subtitle='', logo_path=None, preferred_widths=None, no_truncate_cols=None):
    page_width = 595
    page_height = 842
    margin = 36
    table_width = page_width - (2 * margin)
    row_height = 20
    header_height = 24

    widths = preferred_widths if (preferred_widths and len(preferred_widths) == len(headers)) else _compute_table_widths(headers, rows)
    total_units = sum(widths) or 1
    col_widths = [(w / total_units) * table_width for w in widths]
    no_truncate_cols = set(no_truncate_cols or [])

    title_y = page_height - margin

    logo_data = None
    logo_size = None
    if logo_path and os.path.exists(logo_path):
        with open(logo_path, 'rb') as logo_file:
            candidate = logo_file.read()
        size = _get_jpeg_size(candidate)
        if size:
            logo_data = candidate
            logo_size = size
            title_y -= 70

    def truncate_cell(text, col_width, col_idx):
        cleaned = _pdf_escape(text)
        if col_idx in no_truncate_cols:
            return cleaned
        max_chars = max(3, int((col_width - 8) / 5.5))
        if len(cleaned) > max_chars:
            return cleaned[:max(0, max_chars - 3)] + "..."
        return cleaned

    rendered_rows = [
        [truncate_cell(cell, col_widths[idx], idx) for idx, cell in enumerate(row)]
        for row in rows
    ] if rows else [["Aucune donnee disponible"] + [''] * (len(headers) - 1)]

    table_top = title_y - 52
    available_height = table_top - margin
    rows_per_page = max(8, int((available_height - header_height) / row_height))
    pages = [
        rendered_rows[i:i + rows_per_page]
        for i in range(0, max(1, len(rendered_rows)), rows_per_page)
    ]

    objects = []
    objects.append(b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj")

    page_count = len(pages)
    first_page_obj = 3
    kids_refs = " ".join(f"{first_page_obj + i * 2} 0 R" for i in range(page_count))
    objects.append(f"2 0 obj << /Type /Pages /Kids [{kids_refs}] /Count {page_count} >> endobj".encode('ascii'))

    regular_font_obj_id = first_page_obj + page_count * 2
    bold_font_obj_id = regular_font_obj_id + 1
    image_obj_id = bold_font_obj_id + 1 if logo_data else None

    for i, page_rows in enumerate(pages):
        page_obj_id = first_page_obj + i * 2
        content_obj_id = page_obj_id + 1
        content_parts = []
        if logo_data and logo_size:
            width, height = logo_size
            max_width = 140
            max_height = 55
            scale = min(max_width / width, max_height / height)
            draw_w = width * scale
            draw_h = height * scale
            content_parts.extend([
                "q",
                f"{draw_w:.2f} 0 0 {draw_h:.2f} 40 770 cm",
                "/Im0 Do",
                "Q",
            ])

        current_title_y = title_y + 20
        content_parts.extend([
            "BT", "/F2 15 Tf", f"{margin} {current_title_y:.2f} Td", f"({_pdf_escape(title)}) Tj", "ET",
        ])
        if subtitle:
            content_parts.extend([
                "BT", "/F1 10 Tf", f"{margin} {current_title_y - 18:.2f} Td", f"({_pdf_escape(subtitle)}) Tj", "ET",
            ])
        content_parts.extend([
            "BT", "/F1 9 Tf", f"{page_width - margin - 70} {current_title_y:.2f} Td", f"(Page {i + 1}/{page_count}) Tj", "ET",
        ])

        y_top = table_top
        row_count = len(page_rows)
        table_height = header_height + (row_count * row_height)
        y_bottom = y_top - table_height

        content_parts.extend([
            "0.94 0.94 0.94 rg",
            f"{margin:.2f} {y_top - header_height:.2f} {table_width:.2f} {header_height:.2f} re f",
            "0 0 0 rg",
            "0.2 w",
            f"{margin:.2f} {y_top:.2f} m {margin + table_width:.2f} {y_top:.2f} l S",
            f"{margin:.2f} {y_top - header_height:.2f} m {margin + table_width:.2f} {y_top - header_height:.2f} l S",
        ])
        for row_idx in range(row_count):
            y_line = y_top - header_height - ((row_idx + 1) * row_height)
            content_parts.append(f"{margin:.2f} {y_line:.2f} m {margin + table_width:.2f} {y_line:.2f} l S")

        x_cursor = margin
        content_parts.append(f"{x_cursor:.2f} {y_top:.2f} m {x_cursor:.2f} {y_bottom:.2f} l S")
        for col_w in col_widths:
            x_cursor += col_w
            content_parts.append(f"{x_cursor:.2f} {y_top:.2f} m {x_cursor:.2f} {y_bottom:.2f} l S")

        x_cursor = margin + 4
        for col_idx, header in enumerate(headers):
            content_parts.extend([
                "BT", "/F2 9 Tf", f"{x_cursor:.2f} {y_top - 16:.2f} Td", f"({_pdf_escape(header)}) Tj", "ET",
            ])
            x_cursor += col_widths[col_idx]

        for row_idx, row in enumerate(page_rows):
            y_text = y_top - header_height - (row_idx * row_height) - 14
            x_cursor = margin + 4
            for col_idx in range(len(headers)):
                cell = row[col_idx] if col_idx < len(row) else ''
                content_parts.extend([
                    "BT", "/F1 9 Tf", f"{x_cursor:.2f} {y_text:.2f} Td", f"({_pdf_escape(cell)}) Tj", "ET",
                ])
                x_cursor += col_widths[col_idx]

        content = "\n".join(content_parts).encode('latin-1', errors='replace')
        xobject_part = f" /XObject << /Im0 {image_obj_id} 0 R >>" if image_obj_id else ""
        objects.append(
            f"{page_obj_id} 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            f"/Resources << /Font << /F1 {regular_font_obj_id} 0 R /F2 {bold_font_obj_id} 0 R >>{xobject_part} >> "
            f"/Contents {content_obj_id} 0 R >> endobj".encode('ascii')
        )
        objects.append(
            f"{content_obj_id} 0 obj << /Length {len(content)} >> stream\n".encode('ascii')
            + content
            + b"\nendstream endobj"
        )

    objects.append(
        f"{regular_font_obj_id} 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj".encode('ascii')
    )
    objects.append(
        f"{bold_font_obj_id} 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >> endobj".encode('ascii')
    )
    if logo_data and logo_size:
        width, height = logo_size
        objects.append(
            f"{image_obj_id} 0 obj << /Type /XObject /Subtype /Image /Width {width} /Height {height} "
            f"/ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length {len(logo_data)} >> stream\n".encode('ascii')
            + logo_data
            + b"\nendstream endobj"
        )

    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(len(pdf))
        pdf.extend(obj + b"\n")
    xref_pos = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode('ascii'))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode('ascii'))
    pdf.extend(f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF".encode('ascii'))
    return bytes(pdf)


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


def seed_default_class_questions():
    scopes = [
        ('L1', L1_LABEL),
        ('L2', TRONC_COMMUN_LABEL),
        ('L2', 'I'),
        ('L2', 'IMT'),
        ('L2', 'EEA'),
        ('L3', TRONC_COMMUN_LABEL),
        ('L3', 'I'),
        ('L3', 'IMT'),
        ('L3', 'EEA'),
    ]
    existing = {
        (q.class_name, q.filiere_name, q.volet_name, q.question_text)
        for q in ClassQuestion.query.all()
    }
    to_insert = []
    for class_name, filiere_name in scopes:
        for volet_name, questions in DEFAULT_QUESTION_BANK.items():
            for question_text, response_type in questions:
                key = (class_name, filiere_name, volet_name, question_text)
                if key in existing:
                    continue
                to_insert.append(
                    ClassQuestion(
                        class_name=class_name,
                        filiere_name=filiere_name,
                        volet_name=volet_name,
                        question_text=question_text,
                        response_type=response_type,
                    )
                )
                existing.add(key)
    if to_insert:
        db.session.add_all(to_insert)
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


def _avg(values):
    return (sum(values) / len(values)) if values else 0


def build_response_metric_snapshots(responses):
    if not responses:
        return []

    response_ids = [resp.id for resp in responses]
    scale_answers = ClassQuestionAnswer.query.filter(
        ClassQuestionAnswer.survey_response_id.in_(response_ids),
        ClassQuestionAnswer.response_type == 'scale',
    ).all()

    answer_class_names = {ans.class_name for ans in scale_answers if ans.class_name}
    question_volet_map = {
        (q.class_name, q.question_text): q.volet_name
        for q in ClassQuestion.query.filter(ClassQuestion.class_name.in_(answer_class_names)).all()
    } if answer_class_names else {}

    scales_by_response = {
        resp.id: {'all': [], 'enseignement': [], 'enseignant': [], 'organisation': [], 'infrastructures': []}
        for resp in responses
    }

    for ans in scale_answers:
        try:
            numeric_value = int(ans.answer_value)
        except (TypeError, ValueError):
            continue
        bucket = scales_by_response.get(ans.survey_response_id)
        if not bucket:
            continue
        bucket['all'].append(numeric_value)
        volet_name = question_volet_map.get((ans.class_name, ans.question_text), 'enseignement')
        if volet_name not in bucket:
            volet_name = 'enseignement'
        bucket[volet_name].append(numeric_value)

    snapshots = []
    for resp in responses:
        scales = scales_by_response.get(resp.id, {})
        global_avg = _avg(scales.get('all', []))
        enseignement_avg = _avg(scales.get('enseignement', []))
        enseignant_avg = _avg(scales.get('enseignant', []))
        organisation_avg = _avg(scales.get('organisation', []))
        infrastructures_avg = _avg(scales.get('infrastructures', []))

        professor_motivation = resp.professor_motivation if resp.professor_motivation > 0 else round(enseignant_avg or global_avg, 2)
        tools_methodology = resp.tools_methodology if resp.tools_methodology > 0 else round(enseignement_avg or global_avg, 2)
        explanations_clarity = resp.explanations_clarity if resp.explanations_clarity > 0 else round(enseignement_avg or global_avg, 2)

        snapshots.append({
            'involvement': resp.involvement if resp.involvement > 0 else round(enseignement_avg or global_avg, 2),
            'initial_knowledge': resp.initial_knowledge if resp.initial_knowledge > 0 else round(global_avg, 2),
            'current_knowledge': resp.current_knowledge if resp.current_knowledge > 0 else round(global_avg, 2),
            'professor_motivation': professor_motivation,
            'tools_methodology': tools_methodology,
            'examples_exercises': resp.examples_exercises if resp.examples_exercises > 0 else round(enseignement_avg or global_avg, 2),
            'explanations_clarity': explanations_clarity,
            'schedule_organization': resp.schedule_organization if resp.schedule_organization > 0 else round(organisation_avg or global_avg, 2),
            'infrastructure_quality': resp.infrastructure_quality if resp.infrastructure_quality > 0 else round(infrastructures_avg or global_avg, 2),
            'overall_satisfaction': resp.overall_satisfaction if resp.overall_satisfaction > 0 else round(global_avg, 2),
            'practical_skills_yes': 1 if (resp.practical_skills == 'oui' or global_avg >= 6) else 0,
            'course_organization_yes': 1 if (resp.course_organization == 'oui' or (organisation_avg or global_avg) >= 6) else 0,
        })
    return snapshots


def get_standard_classes():
    return Classe.query.filter(Classe.nom.in_(CLASS_LEVELS)).order_by(Classe.nom.asc()).all()


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

    submitted_answers = {}
    if request.method == 'POST':
        submitted_answers = request.form.to_dict(flat=True)
        feedback = request.form.get('feedback', '').strip()
        extra_answers = []
        missing_count = 0
        scale_values_by_volet = {volet: [] for volet in VOLETS}
        all_scale_values = []

        for question in class_questions:
            field_name = f'class_question_{question.id}'
            value = request.form.get(field_name, '').strip()
            if question.response_type == 'scale':
                if value not in {str(i) for i in range(11)}:
                    missing_count += 1
                else:
                    extra_answers.append((question, value))
                    numeric_value = int(value)
                    all_scale_values.append(numeric_value)
                    volet_name = question.volet_name if question.volet_name in VOLETS else 'enseignement'
                    scale_values_by_volet[volet_name].append(numeric_value)
            else:
                if not value:
                    missing_count += 1
                else:
                    extra_answers.append((question, value[:500]))

        if missing_count == 0:
            global_avg = round(_avg(all_scale_values), 2)
            enseignement_avg = round(_avg(scale_values_by_volet['enseignement']) or global_avg, 2)
            enseignant_avg = round(_avg(scale_values_by_volet['enseignant']) or global_avg, 2)
            organisation_avg = round(_avg(scale_values_by_volet['organisation']) or global_avg, 2)
            infrastructures_avg = round(_avg(scale_values_by_volet['infrastructures']) or global_avg, 2)

            new_response = SurveyResponse(
                filiere_name=filiere_name,
                class_name=class_name,
                subject_name=subject_name,
                involvement=int(round(enseignement_avg)),
                initial_knowledge=int(round(global_avg)),
                current_knowledge=int(round(global_avg)),
                professor_motivation=int(round(enseignant_avg)),
                tools_methodology=int(round(enseignement_avg)),
                examples_exercises=int(round(enseignement_avg)),
                explanations_clarity=int(round(enseignement_avg)),
                practical_skills='oui' if global_avg >= 6 else 'non',
                course_organization='oui' if organisation_avg >= 6 else 'non',
                schedule_organization=int(round(organisation_avg)),
                infrastructure_quality=int(round(infrastructures_avg)),
                overall_satisfaction=int(round(global_avg)),
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

        flash(
            f'Veuillez voter/répondre dans les autres champs avant de soumettre ({missing_count} question(s) manquante(s)).',
            'danger'
        )

    active_questionnaire = Questionnaire.query.filter_by(is_active=True).order_by(Questionnaire.created_at.desc()).first()
    return render_template(
        'survey.html',
        active_questionnaire=active_questionnaire,
        class_questions=class_questions,
        volets=VOLETS,
        volet_labels=VOLET_LABELS,
        questions_by_volet=questions_by_volet,
        submitted_answers=submitted_answers,
    )


@app.route('/admin')
def admin():
    if not ensure_admin_session():
        return redirect(url_for('login'))

    ensure_default_classes()
    classes = get_standard_classes()
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

    subject = Matiere.query.filter(
        Matiere.nom == subject_name,
        Matiere.class_name.in_([classe_name, CAMPAIGN_GLOBAL_LABEL]),
    ).filter(
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


@app.route('/tokens/export.csv', methods=['GET'])
def export_tokens_csv():
    if not ensure_admin_session():
        return redirect(url_for('login'))

    campaign_id = request.args.get('campaign_id', type=int)
    only_unused = request.args.get('only_unused', '1').lower() in {'1', 'true', 'yes', 'on'}

    query = EvaluationToken.query
    if campaign_id:
        query = query.filter_by(campaign_id=campaign_id)
    if only_unused:
        query = query.filter_by(is_used=False)

    tokens = query.order_by(EvaluationToken.created_at.desc()).all()
    campaigns_by_id = {c.id: c.name for c in EvaluationCampaign.query.all()}

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        'token',
        'campagne',
        'filiere',
        'classe',
        'matiere',
        'utilise',
        'date_creation',
        'date_utilisation',
    ])
    for token in tokens:
        writer.writerow([
            token.token,
            campaigns_by_id.get(token.campaign_id, 'Sans campagne'),
            token.filiere_name,
            token.class_name,
            token.subject_name,
            'oui' if token.is_used else 'non',
            token.created_at.strftime('%Y-%m-%d %H:%M:%S') if token.created_at else '',
            token.used_at.strftime('%Y-%m-%d %H:%M:%S') if token.used_at else '',
        ])

    suffix = f"_campaign_{campaign_id}" if campaign_id else ""
    filename = f"tokens_export{suffix}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename={filename}'},
    )


@app.route('/tokens/export.pdf', methods=['GET'])
def export_tokens_pdf():
    if not ensure_admin_session():
        return redirect(url_for('login'))

    campaign_id = request.args.get('campaign_id', type=int)
    only_unused = request.args.get('only_unused', '1').lower() in {'1', 'true', 'yes', 'on'}

    query = EvaluationToken.query
    if campaign_id:
        query = query.filter_by(campaign_id=campaign_id)
    if only_unused:
        query = query.filter_by(is_used=False)

    tokens = query.order_by(EvaluationToken.created_at.desc()).all()
    campaigns_by_id = {c.id: c.name for c in EvaluationCampaign.query.all()}
    rows = []
    for index, token in enumerate(tokens, start=1):
        rows.append([
            index,
            token.token,
            campaigns_by_id.get(token.campaign_id, 'Sans campagne'),
            token.filiere_name,
            token.class_name,
            token.subject_name,
            'utilisé' if token.is_used else 'disponible',
            token.created_at.strftime('%Y-%m-%d') if token.created_at else '',
        ])

    pdf_bytes = build_table_pdf(
        title="Export des tokens générés",
        subtitle=(
            f"Filtres: campagne={campaign_id or 'toutes'} | non_utilises={only_unused} | "
            f"total={len(tokens)} | genere le {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"
        ),
        headers=['#', 'Token', 'Campagne', 'Filiere', 'Classe', 'Matiere', 'Statut', 'Cree le'],
        rows=rows,
        logo_path=PDF_LOGO_PATH,
        preferred_widths=[2, 9, 9, 10, 4, 13, 5, 8],
        no_truncate_cols=[1],
    )
    suffix = f"_campaign_{campaign_id}" if campaign_id else ""
    filename = f"tokens_export{suffix}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.pdf"
    return Response(
        pdf_bytes,
        mimetype='application/pdf',
        headers={'Content-Disposition': f'attachment; filename={filename}'},
    )


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
    is_all_subject_role = (not teacher_subject_name) or teacher_subject_name.strip().upper() == 'ALL'

    if not is_all_subject_role:
        filiere_name = None
        classe_name = None
        subject_name = teacher_subject_name
    else:
        subject_name = requested_subject_name

    responses = build_dashboard_query(filiere_name, classe_name, subject_name).all()
    total = len(responses)
    comments = [r.feedback for r in responses if r.feedback]

    metric_snapshots = build_response_metric_snapshots(responses)
    snapshot_total = len(metric_snapshots)
    metrics = {
        'total': total,
        'satisfaction': round(_avg([m['overall_satisfaction'] for m in metric_snapshots]), 2) if snapshot_total else 0,
        'pedagogy': round(_avg([
            (m['professor_motivation'] + m['tools_methodology'] + m['explanations_clarity']) / 3
            for m in metric_snapshots
        ]), 2) if snapshot_total else 0,
        'organization': round(_avg([m['schedule_organization'] for m in metric_snapshots]), 2) if snapshot_total else 0,
        'infrastructure': round(_avg([m['infrastructure_quality'] for m in metric_snapshots]), 2) if snapshot_total else 0,
    }

    classes = get_standard_classes()
    matieres = Matiere.query.all()
    return render_template(
        'teacher_dashboard.html',
        metrics=metrics,
        comments=comments[:30],
        filieres=ALL_FILIERES,
        classes=classes,
        matieres=matieres,
        teacher_subject_name=teacher_subject_name,
        is_all_subject_role=is_all_subject_role,
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

    metric_snapshots = build_response_metric_snapshots(responses)
    avg_involvement = _avg([m['involvement'] for m in metric_snapshots])
    avg_initial_knowledge = _avg([m['initial_knowledge'] for m in metric_snapshots])
    avg_current_knowledge = _avg([m['current_knowledge'] for m in metric_snapshots])
    avg_professor_motivation = _avg([m['professor_motivation'] for m in metric_snapshots])
    avg_tools_methodology = _avg([m['tools_methodology'] for m in metric_snapshots])
    avg_examples_exercises = _avg([m['examples_exercises'] for m in metric_snapshots])
    avg_explanations_clarity = _avg([m['explanations_clarity'] for m in metric_snapshots])
    avg_satisfaction_general = _avg([m['overall_satisfaction'] for m in metric_snapshots])
    avg_schedule_organization = _avg([m['schedule_organization'] for m in metric_snapshots])
    avg_infrastructure_quality = _avg([m['infrastructure_quality'] for m in metric_snapshots])
    practical_skills_yes = sum(m['practical_skills_yes'] for m in metric_snapshots)
    course_organization_yes = sum(m['course_organization_yes'] for m in metric_snapshots)

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
    metric_snapshots = build_response_metric_snapshots(responses)
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
            'satisfaction': round(_avg([m['overall_satisfaction'] for m in metric_snapshots]), 2),
            'organization': round(_avg([m['schedule_organization'] for m in metric_snapshots]), 2),
            'infrastructure': round(_avg([m['infrastructure_quality'] for m in metric_snapshots]), 2),
            'pedagogy': round(_avg([
                (m['professor_motivation'] + m['tools_methodology'] + m['explanations_clarity']) / 3
                for m in metric_snapshots
            ]), 2),
        }

    classes = get_standard_classes()
    matieres = Matiere.query.order_by(Matiere.nom.asc()).all()
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


@app.route('/dashboard/export.pdf', methods=['GET'])
def dashboard_export_pdf():
    if not ensure_admin_session():
        return redirect(url_for('login'))

    filiere_name = request.args.get('filiere', '').strip() or None
    classe_name = request.args.get('classe', '').strip() or None
    subject_name = request.args.get('matiere', '').strip() or None

    responses = build_dashboard_query(filiere_name, classe_name, subject_name).all()
    rows = [
        [
            idx,
            r.filiere_name,
            r.class_name,
            r.subject_name,
            r.overall_satisfaction,
            r.schedule_organization,
            r.infrastructure_quality,
            r.professor_motivation,
            r.tools_methodology,
        ]
        for idx, r in enumerate(responses, start=1)
    ]
    pdf_bytes = build_table_pdf(
        title="Export dashboard décisionnel",
        subtitle=(
            f"Filtres: filiere={filiere_name or 'toutes'} | classe={classe_name or 'toutes'} | "
            f"matiere={subject_name or 'toutes'} | total={len(responses)}"
        ),
        headers=['#', 'Filiere', 'Classe', 'Matiere', 'Satisf.', 'Organ.', 'Infra.', 'Motiv.', 'Metho.'],
        rows=rows,
        logo_path=PDF_LOGO_PATH,
        preferred_widths=[2, 8, 5, 11, 5, 5, 5, 5, 5],
        no_truncate_cols=[3],
    )
    filename = f"dashboard_export_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.pdf"
    return Response(
        pdf_bytes,
        mimetype='application/pdf',
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

    is_all_subject_role = (not assigned_subject_name) or assigned_subject_name.upper() == 'ALL'
    if (not is_all_subject_role) and not Matiere.query.filter_by(nom=assigned_subject_name).first():
        flash('La matière associée à l\'enseignant est invalide.', 'danger')
        return redirect(url_for('admin'))

    teacher = Teacher(
        username=username,
        password_hash=generate_password_hash(password),
        full_name=full_name or None,
        assigned_subject_name=None if is_all_subject_role else assigned_subject_name,
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

    # Normalise les anciennes valeurs de classe de type "L2 I", "L3 IMT", etc.
    for level in ('L2', 'L3'):
        for filiere in FILIERES_ITER:
            legacy_class = f"{level} {filiere}"
            db.session.execute(
                text(
                    "UPDATE survey_response "
                    "SET class_name = :level, filiere_name = :filiere "
                    "WHERE class_name = :legacy_class"
                ),
                {"level": level, "filiere": filiere, "legacy_class": legacy_class},
            )
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
        seed_default_class_questions()
        app.run(host='0.0.0.0', port=5000)
