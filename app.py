"""Interface Streamlit : contrôle d'accès parking par lecture de plaques (LAPI).

Affiche le flux vidéo annoté, gère une liste blanche de plaques autorisées et
une zone de détection (ROI) réglable.
"""
import os
import site
import sys
import time

import cv2
import streamlit as st


def _register_nvidia_dll_dirs() -> None:
    """Injecte les DLL cuDNN/cuBLAS (pip nvidia-*) dans le PATH Windows.

    Indispensable avant le premier import d'onnxruntime.
    """
    for packages_dir in site.getsitepackages():
        for lib in ("cudnn", "cublas"):
            dll_dir = os.path.join(packages_dir, "nvidia", lib, "bin")
            if os.path.exists(dll_dir):
                os.add_dll_directory(dll_dir)


_register_nvidia_dll_dirs()

# Ajout du chemin pour trouver les modules locaux (avant les imports src.*)
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.append(_HERE)

from src.config import YOLO_MODEL, PROVIDERS, OCR_MODEL, CHARS_PATH  # noqa: E402
from src.models.ocr import load_ocr                                  # noqa: E402
from src.models.yolo import load_yolo                                 # noqa: E402
from src.pipeline.core import make_initial_state, run_pipeline        # noqa: E402

# ── Constantes UI ─────────────────────────────────────────────────────────────
FRAME_WIDTH = 640
FRAME_HEIGHT = 480
DEFAULT_WHITELIST = ["AA-123-BB"]
DEMO_VIDEO_PATH = os.path.join(_HERE, "rush_2.avi")
LOGO_PATH = "static/logo.png"
NO_PLATE_TEXT = "Aucune"


@st.cache_resource
def load_models():
    """Charge YOLO + OCR une seule fois (mis en cache par Streamlit)."""
    try:
        yolo = load_yolo(YOLO_MODEL, PROVIDERS)
        ocr = load_ocr(OCR_MODEL, CHARS_PATH, PROVIDERS)
        return yolo, ocr
    except Exception as e:
        st.error(f"Erreur de chargement des modèles : {e}")
        return None, None


def init_session_state() -> None:
    if "whitelist" not in st.session_state:
        st.session_state.whitelist = list(DEFAULT_WHITELIST)
    if "run_camera" not in st.session_state:
        st.session_state.run_camera = False


def render_whitelist_sidebar() -> None:
    """Formulaire d'ajout et liste des plaques autorisées (avec suppression)."""
    st.sidebar.header("Gestion des Autorisés")

    with st.sidebar.form(key="add_plate_form", clear_on_submit=True):
        new_plate = st.text_input("Ajouter une plaque (Ex: AB-123-CD)")
        submitted = st.form_submit_button(label="Ajouter")
        if submitted and new_plate:
            if new_plate not in st.session_state.whitelist:
                st.session_state.whitelist.append(new_plate)
                st.sidebar.success(f"{new_plate} ajouté.")

    st.sidebar.subheader("Plaques Enregistrées")
    plates_to_remove = []
    for plate in st.session_state.whitelist:
        col_name, col_delete = st.sidebar.columns([3, 1])
        col_name.markdown(f"**{plate}**")
        if col_delete.button("❌", key=f"del_{plate}"):
            plates_to_remove.append(plate)

    for plate in plates_to_remove:
        st.session_state.whitelist.remove(plate)
        st.rerun()


def render_roi_sidebar() -> tuple:
    """Curseurs de la zone de détection — retourne (x, y, largeur, hauteur)."""
    st.sidebar.markdown("---")
    st.sidebar.subheader("Zone de Détection (ROI)")
    roi_x = st.sidebar.slider("X", 0, FRAME_WIDTH, 0, key="roi_x")
    roi_y = st.sidebar.slider("Y", 0, FRAME_HEIGHT, 0, key="roi_y")
    roi_w = st.sidebar.slider("Largeur", 50, FRAME_WIDTH, FRAME_WIDTH, key="roi_w")
    roi_h = st.sidebar.slider("Hauteur", 50, FRAME_HEIGHT, FRAME_HEIGHT, key="roi_h")
    return roi_x, roi_y, roi_w, roi_h


def render_sidebar() -> tuple:
    """Barre latérale complète — retourne la ROI choisie."""
    if os.path.exists(LOGO_PATH):
        st.sidebar.image(LOGO_PATH, use_container_width=True)
    else:
        st.sidebar.title("Parking LAPI")

    render_whitelist_sidebar()
    return render_roi_sidebar()


def render_main_layout() -> tuple:
    """Colonnes principales — retourne (video_placeholder, plate_html, status_html)."""
    col_main, col_data = st.columns([3, 1])

    with col_main:
        st.title("Flux Vidéo en Direct")
        video_placeholder = st.empty()
        label = "Arrêter la vidéo" if st.session_state.run_camera else "Démarrer la vidéo"
        if st.button(label):
            st.session_state.run_camera = not st.session_state.run_camera
            st.rerun()

    with col_data:
        st.title("Résultat")
        st.markdown(
            '<div style="padding:20px; background-color:#f4f6f9; '
            'border-radius:10px; text-align:center;">',
            unsafe_allow_html=True,
        )
        st.subheader("Plaque Détectée")
        plate_html = st.empty()
        status_html = st.empty()
        st.markdown("</div>", unsafe_allow_html=True)

    return video_placeholder, plate_html, status_html


def detect_plate_in_roi(frame, roi, state, yolo, ocr) -> tuple:
    """Lance le pipeline sur la ROI — retourne (texte_détecté, nouvel_état)."""
    roi_x, roi_y, roi_w, roi_h = roi
    cropped = frame[roi_y:roi_y + roi_h, roi_x:roi_x + roi_w]

    if not (yolo and ocr and cropped.size > 0):
        return NO_PLATE_TEXT, state

    try:
        _, detections, state, _ = run_pipeline(cropped, state, yolo, ocr)
        for det in detections:
            if det.get("text"):
                return det["text"], state
    except Exception:
        # La frame est simplement affichée sans détection ; on ne casse pas la boucle
        pass
    return NO_PLATE_TEXT, state


def annotate_frame(frame, roi, fps) -> None:
    """Dessine la ROI et le compteur de FPS sur la frame (en place)."""
    roi_x, roi_y, roi_w, roi_h = roi
    cv2.rectangle(frame, (roi_x, roi_y), (roi_x + roi_w, roi_y + roi_h), (0, 0, 255), 2)
    cv2.putText(frame, "Zone a regarder", (roi_x, roi_y - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
    cv2.putText(frame, f"FPS: {fps:.1f}", (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)


def display_result(plate_html, status_html, plate_text: str) -> None:
    """Affiche la plaque détectée et son statut vis-à-vis de la liste blanche."""
    if plate_text != NO_PLATE_TEXT:
        authorized = plate_text in st.session_state.whitelist
        status = "Autorisé" if authorized else "Inconnu ou Refusé"
        color = "green" if authorized else "red"
    else:
        status, color = "---", "gray"

    plate_html.markdown(
        f"<h1 style='color: #2b2b2b; font-family: monospace; "
        f"letter-spacing: 2px;'>{plate_text}</h1>",
        unsafe_allow_html=True,
    )
    status_html.markdown(
        f"<h3 style='color: {color}; font-weight: bold;'>{status}</h3>",
        unsafe_allow_html=True,
    )


def run_video_loop(roi, video_placeholder, plate_html, status_html, yolo, ocr) -> None:
    """Boucle de lecture vidéo synchronisée temps réel (saut de frames si en retard)."""
    cap = cv2.VideoCapture(DEMO_VIDEO_PATH)  # Lecture d'un fichier vidéo pour la démo
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)

    state = make_initial_state() if yolo else None

    video_fps = cap.get(cv2.CAP_PROP_FPS)
    if not video_fps or video_fps <= 0:
        video_fps = 30.0

    start_time = time.time()
    prev_time = start_time

    while st.session_state.run_camera:
        # Si l'algorithme est en retard, on saute des frames pour rester temps réel
        elapsed = time.time() - start_time
        expected_frame = int(elapsed * video_fps)
        current_frame_pos = int(cap.get(cv2.CAP_PROP_POS_FRAMES))
        if expected_frame > current_frame_pos:
            cap.set(cv2.CAP_PROP_POS_FRAMES, expected_frame)

        ret, frame = cap.read()
        if not ret:
            st.warning("Fin de la vidéo atteinte.")
            st.session_state.run_camera = False
            break

        # FPS de traitement
        current_time = time.time()
        fps = 1 / (current_time - prev_time) if current_time - prev_time > 0 else 0
        prev_time = current_time

        # Taille fixe pour correspondre aux curseurs de la ROI
        frame = cv2.resize(frame, (FRAME_WIDTH, FRAME_HEIGHT))

        plate_text, state = detect_plate_in_roi(frame, roi, state, yolo, ocr)

        annotate_frame(frame, roi, fps)
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        video_placeholder.image(frame_rgb, channels="RGB", use_container_width=True)

        display_result(plate_html, status_html, plate_text)

    cap.release()


def main() -> None:
    st.set_page_config(page_title="LAPI Parking", layout="wide",
                       initial_sidebar_state="expanded")
    init_session_state()

    yolo, ocr = load_models()
    roi = render_sidebar()
    video_placeholder, plate_html, status_html = render_main_layout()

    if st.session_state.run_camera:
        run_video_loop(roi, video_placeholder, plate_html, status_html, yolo, ocr)


main()
