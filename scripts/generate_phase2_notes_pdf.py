#!/usr/bin/env python3
"""
Phase 2: 3D Neural Photogrammetry & Mesh Processing
Comprehensive Master Study Guide & Viva Reference Manual (Single Source of Truth)

This script compiles a comprehensive, publication-grade academic PDF
explaining every concept, algorithm, code logic, and forensic decision
in Phase 2 of the AI Forensics & 3D Crime Scene Reconstruction project.
"""

import os
import sys
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfgen import canvas

# Output Path
ROOT_DIR = Path(__file__).resolve().parent.parent
PDF_OUTPUT_PATH = ROOT_DIR / "Phase_2_3D_Neural_Photogrammetry_Master_Notes.pdf"

# ----------------------------------------------------------------------
# Professional Academic Color Palette
# ----------------------------------------------------------------------
NAVY_PRIMARY    = colors.HexColor("#0D233A")  # Deep forensic navy
BLUE_SECONDARY  = colors.HexColor("#1A5F7A")  # Technical blue
TEAL_ACCENT     = colors.HexColor("#159895")  # Algorithmic teal
GOLD_ACCENT     = colors.HexColor("#D49B28")  # Highlight gold
CHARCOAL_TEXT   = colors.HexColor("#1E293B")  # Deep charcoal body text
LIGHT_BG_BLUE   = colors.HexColor("#F0F7FA")  # Concept callout background
LIGHT_BG_GREEN  = colors.HexColor("#F2FAF7")  # Algorithm callout background
LIGHT_BG_AMBER  = colors.HexColor("#FEF9EE")  # Professor viva background
LIGHT_BG_PURPLE = colors.HexColor("#F8F5FC")  # Forensic context background
BORDER_BLUE     = colors.HexColor("#2B6CB0")
BORDER_GREEN    = colors.HexColor("#288258")
BORDER_AMBER    = colors.HexColor("#D97706")
BORDER_PURPLE   = colors.HexColor("#7C3AED")
RULE_COLOR      = colors.HexColor("#CBD5E1")
TABLE_HEADER_BG = colors.HexColor("#1E3A5F")

# ----------------------------------------------------------------------
# Numbered Canvas for Running Headers and Footers
# ----------------------------------------------------------------------
class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_header_footer(num_pages)
            super().showPage()
        super().save()

    def draw_header_footer(self, total_pages):
        if self._pageNumber == 1:
            return

        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#64748B"))

        # Running Header
        self.drawString(36, letter[1] - 32, "AI FORENSICS: 3D CRIME SCENE RECONSTRUCTION")
        self.drawRightString(letter[0] - 36, letter[1] - 32, "PHASE 2 MASTER NOTES: NEURAL PHOTOGRAMMETRY & MESHING")
        self.setStrokeColor(RULE_COLOR)
        self.setLineWidth(0.6)
        self.line(36, letter[1] - 36, letter[0] - 36, letter[1] - 36)

        # Running Footer
        self.line(36, 40, letter[0] - 36, 40)
        self.drawString(36, 28, "CONFIDENTIAL & PROPRIETARY — ACADEMIC DEFENSE & VIVA REFERENCE MANUAL")
        page_str = f"Page {self._pageNumber} of {total_pages}"
        self.drawRightString(letter[0] - 36, 28, page_str)
        self.restoreState()


# ----------------------------------------------------------------------
# Document Styles Builder
# ----------------------------------------------------------------------
def create_styles():
    base = getSampleStyleSheet()

    styles = {
        'DocTitle': ParagraphStyle(
            'DocTitle',
            parent=base['Title'],
            fontName='Helvetica-Bold',
            fontSize=23,
            leading=27,
            textColor=NAVY_PRIMARY,
            alignment=0,
            spaceAfter=5
        ),
        'DocSubtitle': ParagraphStyle(
            'DocSubtitle',
            parent=base['Normal'],
            fontName='Helvetica',
            fontSize=10.5,
            leading=15,
            textColor=BLUE_SECONDARY,
            spaceAfter=12
        ),
        'SectionH1': ParagraphStyle(
            'SectionH1',
            parent=base['Heading1'],
            fontName='Helvetica-Bold',
            fontSize=14,
            leading=18,
            textColor=NAVY_PRIMARY,
            spaceBefore=14,
            spaceAfter=5,
            keepWithNext=True
        ),
        'SectionH2': ParagraphStyle(
            'SectionH2',
            parent=base['Heading2'],
            fontName='Helvetica-Bold',
            fontSize=11,
            leading=14.5,
            textColor=BLUE_SECONDARY,
            spaceBefore=10,
            spaceAfter=4,
            keepWithNext=True
        ),
        'SectionH3': ParagraphStyle(
            'SectionH3',
            parent=base['Heading3'],
            fontName='Helvetica-Bold',
            fontSize=9.5,
            leading=12.5,
            textColor=CHARCOAL_TEXT,
            spaceBefore=7,
            spaceAfter=3,
            keepWithNext=True
        ),
        'Body': ParagraphStyle(
            'Body',
            parent=base['BodyText'],
            fontName='Helvetica',
            fontSize=8.5,
            leading=12,
            textColor=CHARCOAL_TEXT,
            spaceAfter=4
        ),
        'BodyBold': ParagraphStyle(
            'BodyBold',
            parent=base['BodyText'],
            fontName='Helvetica-Bold',
            fontSize=8.5,
            leading=12,
            textColor=CHARCOAL_TEXT,
            spaceAfter=4
        ),
        'BulletText': ParagraphStyle(
            'BulletText',
            parent=base['Normal'],
            fontName='Helvetica',
            fontSize=8.5,
            leading=11.8,
            textColor=CHARCOAL_TEXT,
            leftIndent=12,
            spaceAfter=3
        ),
        'CalloutTitle': ParagraphStyle(
            'CalloutTitle',
            parent=base['Normal'],
            fontName='Helvetica-Bold',
            fontSize=9,
            leading=12,
            spaceAfter=3
        ),
        'CalloutText': ParagraphStyle(
            'CalloutText',
            parent=base['Normal'],
            fontName='Helvetica',
            fontSize=8,
            leading=11.5,
            textColor=CHARCOAL_TEXT
        ),
        'TableHeader': ParagraphStyle(
            'TableHeader',
            parent=base['Normal'],
            fontName='Helvetica-Bold',
            fontSize=8,
            leading=10.5,
            textColor=colors.white,
            alignment=0
        ),
        'TableCell': ParagraphStyle(
            'TableCell',
            parent=base['Normal'],
            fontName='Helvetica',
            fontSize=7.5,
            leading=10,
            textColor=CHARCOAL_TEXT
        ),
        'TableCellBold': ParagraphStyle(
            'TableCellBold',
            parent=base['Normal'],
            fontName='Helvetica-Bold',
            fontSize=7.5,
            leading=10,
            textColor=NAVY_PRIMARY
        )
    }
    return styles


# ----------------------------------------------------------------------
# Flowable Helper Utilities
# ----------------------------------------------------------------------
CONTENT_WIDTH = 540  # 8.5" * 72 - 36*2

def make_callout(title, text, bg_color, border_color, title_color, styles):
    title_p = Paragraph(f"<font color='{title_color.hexval()}'><b>{title}</b></font>", styles['CalloutTitle'])
    text_p = Paragraph(text, styles['CalloutText'])
    tbl = Table([[title_p], [text_p]], colWidths=[CONTENT_WIDTH])
    tbl.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), bg_color),
        ('BOX', (0,0), (-1,-1), 1.2, border_color),
        ('LEFTPADDING', (0,0), (-1,-1), 10),
        ('RIGHTPADDING', (0,0), (-1,-1), 10),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('ROUNDEDCORNERS', [4, 4, 4, 4]),
    ]))
    return tbl

def make_algorithm_box(algo_num, algo_name, inputs_str, steps_list, outputs_str, styles):
    content = []
    header_html = f"<b>ALGORITHM {algo_num}: {algo_name.upper()}</b>"
    content.append([Paragraph(f"<font color='#0D233A'>{header_html}</font>", styles['CalloutTitle'])])
    
    in_out = f"<b>Input:</b> {inputs_str}<br/><b>Output:</b> {outputs_str}"
    content.append([Paragraph(in_out, styles['CalloutText'])])
    
    steps_body = "<b>Algorithmic Procedure:</b><br/>"
    for i, step in enumerate(steps_list, 1):
        steps_body += f"&nbsp;&nbsp;<b>Step {i}:</b> {step}<br/>"
    content.append([Paragraph(steps_body, styles['CalloutText'])])

    tbl = Table(content, colWidths=[CONTENT_WIDTH])
    tbl.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), LIGHT_BG_GREEN),
        ('BOX', (0,0), (-1,-1), 1.2, BORDER_GREEN),
        ('LEFTPADDING', (0,0), (-1,-1), 10),
        ('RIGHTPADDING', (0,0), (-1,-1), 10),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('LINEBELOW', (0,0), (0,0), 0.8, colors.HexColor("#A7F3D0")),
        ('ROUNDEDCORNERS', [4, 4, 4, 4]),
    ]))
    return tbl

def make_viva_box(q_num, question, answer_script, why_asked, styles):
    content = []
    q_html = f"<b>VIVA QUESTION #{q_num}: \"{question}\"</b>"
    content.append([Paragraph(f"<font color='#92400E'>{q_html}</font>", styles['CalloutTitle'])])
    
    why_html = f"<i>What the Examiner is testing:</i> {why_asked}"
    content.append([Paragraph(why_html, styles['CalloutText'])])
    
    ans_html = f"<b>Your Model Defense Answer:</b><br/>\"{answer_script}\""
    content.append([Paragraph(ans_html, styles['CalloutText'])])

    tbl = Table(content, colWidths=[CONTENT_WIDTH])
    tbl.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), LIGHT_BG_AMBER),
        ('BOX', (0,0), (-1,-1), 1.2, BORDER_AMBER),
        ('LEFTPADDING', (0,0), (-1,-1), 10),
        ('RIGHTPADDING', (0,0), (-1,-1), 10),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('ROUNDEDCORNERS', [4, 4, 4, 4]),
    ]))
    return tbl

def make_code_box(filename, line_ref, function_name, explanation, styles):
    content = []
    header_html = f"<b>FILE REFERENCE:</b> <font color='#1A5F7A'>{filename}</font> &nbsp;|&nbsp; <b>FUNCTION:</b> <code>{function_name}</code> (Lines {line_ref})"
    content.append([Paragraph(header_html, styles['CalloutTitle'])])
    content.append([Paragraph(explanation, styles['CalloutText'])])
    
    tbl = Table(content, colWidths=[CONTENT_WIDTH])
    tbl.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), LIGHT_BG_BLUE),
        ('BOX', (0,0), (-1,-1), 1.2, BORDER_BLUE),
        ('LEFTPADDING', (0,0), (-1,-1), 10),
        ('RIGHTPADDING', (0,0), (-1,-1), 10),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('ROUNDEDCORNERS', [4, 4, 4, 4]),
    ]))
    return tbl


# ----------------------------------------------------------------------
# Main PDF Builder
# ----------------------------------------------------------------------
def build_pdf():
    doc = SimpleDocTemplate(
        str(PDF_OUTPUT_PATH),
        pagesize=letter,
        leftMargin=36,
        rightMargin=36,
        topMargin=46,
        bottomMargin=46
    )

    styles = create_styles()
    story = []

    # ==================================================================
    # COVER / HEADER BLOCK
    # ==================================================================
    story.append(Paragraph("AI Forensics & 3D Crime Scene Reconstruction", styles['DocTitle']))
    subtitle_text = (
        "<b>Phase 2 Comprehensive Master Notes: 3D Neural Photogrammetry & Mesh Processing</b><br/>"
        "<i>Autonomous Point Cloud Generation, Screened Poisson Surface Reconstruction, "
        "Coordinate Alignment, Normal Voting, Mesh Enhancement & Navigation Grid Pipeline</i>"
    )
    story.append(Paragraph(subtitle_text, styles['DocSubtitle']))
    story.append(HRFlowable(width="100%", thickness=2, color=NAVY_PRIMARY, spaceBefore=0, spaceAfter=8))

    meta_data = [
        [
            Paragraph("<b>Target Domain:</b> Forensic Crime Scene Twins", styles['TableCell']),
            Paragraph("<b>Pipeline Core:</b> DUSt3R ViT + Open3D + Trimesh", styles['TableCell']),
            Paragraph("<b>Primary Input:</b> Uncalibrated 2D Photo Stream", styles['TableCell'])
        ],
        [
            Paragraph("<b>Candidate Degree:</b> B.Tech Final Year", styles['TableCell']),
            Paragraph("<b>Surface Engine:</b> Screened Poisson + Ball Pivoting", styles['TableCell']),
            Paragraph("<b>Deliverable:</b> Metric Normal 3D GLB + NavGrid", styles['TableCell'])
        ]
    ]
    meta_table = Table(meta_data, colWidths=[180, 180, 180])
    meta_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F8FAFC")),
        ('BOX', (0,0), (-1,-1), 1, RULE_COLOR),
        ('INNERGRID', (0,0), (-1,-1), 0.5, RULE_COLOR),
        ('TOPPADDING', (0,0), (-1,-1), 3),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 8))

    notice = (
        "<b>STUDENT VIVA ADVISORY:</b> This document is your <b>complete, self-contained single source of truth</b>. "
        "You do not need to memorize raw Python code lines or abstract mathematical proofs. Every concept "
        "is explained through intuitive forensic analogies, step-by-step algorithms, precise system parameters, "
        "and tailored model defense answers to guarantee absolute mastery during project viva examinations."
    )
    story.append(make_callout("HOW TO STUDY THIS MASTER MANUAL", notice, LIGHT_BG_AMBER, BORDER_AMBER, colors.HexColor("#B45309"), styles))
    story.append(Spacer(1, 10))

    # ==================================================================
    # MODULE 1: FORENSIC FOUNDATIONS & PHOTOGRAMMETRY PARADIGM SHIFT
    # ==================================================================
    story.append(Paragraph("Module 1: Forensic Foundations & The Photogrammetry Paradigm Shift", styles['SectionH1']))
    story.append(HRFlowable(width="100%", thickness=1, color=BLUE_SECONDARY, spaceBefore=0, spaceAfter=6))

    story.append(Paragraph("1.1 The Critical Forensic Problem: Why Traditional Crime Scene Photos Fall Short", styles['SectionH2']))
    story.append(Paragraph(
        "In modern criminalistics, crime scene documentation is governed by the <b>Chain of Custody</b> "
        "and the <b>Locard Exchange Principle</b> (every contact leaves a trace). Physical crime scenes are inherently "
        "fragile: biological fluids decompose, weapons are collected, and room furniture is moved by emergency personnel. "
        "Standard 2D photographic documentation presents three fatal evidentiary flaws:", styles['Body']
    ))
    story.append(Paragraph("<b>1. Complete Lack of 3D Spatial Metricity:</b> Standard 2D camera photos lose all depth information. A photograph cannot verify whether a bullet hole was 1.2 meters or 1.8 meters above the floor once the scene is cleared.", styles['BulletText']))
    story.append(Paragraph("<b>2. Perspective Distortion & Parallax:</b> Wide-angle lenses used in small rooms distort wall angles and relative object distances, leading to conflicting courtroom testimonies.", styles['BulletText']))
    story.append(Paragraph("<b>3. Inability to Test Trajectories or Lines of Sight:</b> Investigators cannot re-examine a witness's line of sight or reconstruct a bullet's 3D spatial trajectory from 2D photo prints.", styles['BulletText']))

    story.append(Paragraph(
        "<b>The Forensic Digital Twin Solution:</b> Our system ingests regular, uncalibrated photos captured "
        "on standard mobile phones and computes an interactive, geometrically accurate, millimeter-scale 3D mesh. "
        "This virtual replica allows ballistics simulation, blood spatter angle analysis, and virtual courtroom walkthroughs.", styles['Body']
    ))

    story.append(Paragraph("1.2 The Failure of Classical Photogrammetry (COLMAP, SIFT, OpenMVS) on Crime Scenes", styles['SectionH2']))
    story.append(Paragraph(
        "For two decades, photogrammetry relied on classical <b>Structure-from-Motion (SfM)</b> pipelines "
        "(such as COLMAP) coupled with <b>Multi-View Stereo (MVS)</b> (such as OpenMVS). In our codebase, "
        "<code>reconstruct.py</code> represents this classical baseline. However, classical SfM relies fundamentally "
        "on hand-crafted feature descriptors (SIFT, ORB). Crime scenes represent the exact failure mode of SIFT:", styles['Body']
    ))

    comp_headers = [Paragraph("<b>Evaluation Dimension</b>", styles['TableHeader']),
                    Paragraph("<b>Classical SfM (COLMAP / SIFT)</b>", styles['TableHeader']),
                    Paragraph("<b>Our Neural Pipeline (DUSt3R)</b>", styles['TableHeader'])]
    comp_rows = [
        [
            Paragraph("<b>Textureless Surfaces</b><br/>(White walls, ceilings)", styles['TableCell']),
            Paragraph("<b>Total Failure:</b> SIFT finds zero feature keypoints on smooth drywall. Walls vanish.", styles['TableCell']),
            Paragraph("<b>Flawless:</b> Global Vision Transformers understand room context and infer 3D planes.", styles['TableCell'])
        ],
        [
            Paragraph("<b>Specular & Wet Media</b><br/>(Blood pools, glass, tiles)", styles['TableCell']),
            Paragraph("<b>Corrupted:</b> Reflected lights create false keypoints, generating erratic floating noise.", styles['TableCell']),
            Paragraph("<b>Robust:</b> Cross-attention predicts surface continuity despite local glare.", styles['TableCell'])
        ],
        [
            Paragraph("<b>Camera Calibration</b><br/>(Focal length, principal point)", styles['TableCell']),
            Paragraph("<b>Strict Requirement:</b> Fails if EXIF metadata is stripped or camera model unknown.", styles['TableCell']),
            Paragraph("<b>Zero Calibration:</b> Directly regresses 3D coordinates without camera parameters.", styles['TableCell'])
        ],
        [
            Paragraph("<b>Runtime & Compute</b><br/>(Matching complexity)", styles['TableCell']),
            Paragraph("<b>Extremely Slow:</b> Pairwise SIFT matching scales quadratically with huge compute.", styles['TableCell']),
            Paragraph("<b>Fast Neural Inference:</b> Feed-forward ViT passes in seconds on Apple Silicon / CUDA.", styles['TableCell'])
        ]
    ]
    comp_table = Table([comp_headers] + comp_rows, colWidths=[120, 210, 210])
    comp_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), TABLE_HEADER_BG),
        ('GRID', (0,0), (-1,-1), 0.5, RULE_COLOR),
        ('TOPPADDING', (0,0), (-1,-1), 3),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
    ]))
    story.append(comp_table)
    story.append(Spacer(1, 8))

    analogy_1 = (
        "<b>Real-World Analogy:</b> Imagine trying to assemble a jigsaw puzzle. SIFT is like a person who can only "
        "connect two puzzle pieces if they both have sharp, high-contrast drawings (like a barcode). If a piece is solid white "
        "(like a wall) or solid red (like a pool of blood), SIFT throws its hands up and quits. "
        "<b>DUSt3R</b>, on the other hand, is like an expert architect looking at the scene with two human eyes. "
        "Even if the wall is blank white, the architect understands human rooms: 'that wall connects the floor to the ceiling, "
        "so its 3D depth must continue smoothly between these corners.' DUSt3R uses learned global context instead of dumb pixel matching."
    )
    story.append(make_callout("CONCEPT ANALOGY: WHY CLASSICAL FAILS & NEURAL SUCCEEDS", analogy_1, LIGHT_BG_BLUE, BORDER_BLUE, BLUE_SECONDARY, styles))
    story.append(Spacer(1, 10))

    # ==================================================================
    # MODULE 2: SYSTEM ARCHITECTURE & SELF-HEALING ENVIRONMENT
    # ==================================================================
    story.append(Paragraph("Module 2: Self-Healing Environment & Execution Architecture", styles['SectionH1']))
    story.append(HRFlowable(width="100%", thickness=1, color=BLUE_SECONDARY, spaceBefore=0, spaceAfter=6))

    story.append(Paragraph("2.1 The Multi-Environment Challenge in Native 3D Reconstruction", styles['SectionH2']))
    story.append(Paragraph(
        "A 3D reconstruction pipeline orchestrates deep learning frameworks (PyTorch), "
        "linear algebra computational libraries (Open3D, SciPy, NumPy), 3D format serializes (Trimesh), "
        "and hardware acceleration runtimes (Apple Metal MPS or NVIDIA CUDA). If executed in an improper virtual "
        "environment or under unconstrained multi-threading, native C++ extensions crash silently. "
        "Our pipeline in <code>reconstruct_dust3r.py</code> incorporates autonomous self-healing routines:", styles['Body']
    ))

    algo1_steps = [
        "Read current executable interpreter path via <code>sys.executable</code>.",
        "Check if running in a known configured virtual environment (e.g., <code>threat_backend/venv</code> or <code>dust3r/venv</code>).",
        "If running in an unconfigured default Python, traverse filesystem hierarchy to find project-specific venv with precompiled PyTorch/Metal binaries.",
        "If a valid target interpreter is discovered, seamlessly re-spawn the entire script process with exact CLI arguments using <code>os.execv()</code>.",
        "If no virtual environment is found, log an informative diagnostic and continue with standard system fallback."
    ]
    story.append(make_algorithm_box(
        "1", "Self-Bootstrapping Virtual Environment Selector (auto_switch_venv)",
        "Current executing process, argv parameters, filesystem directory tree",
        algo1_steps,
        "Zero-configuration execution in the correct Python native environment",
        styles
    ))
    story.append(Spacer(1, 6))

    code_desc_1 = (
        "In <code>reconstruct_dust3r.py</code> lines 39-58, <code>auto_switch_venv()</code> prevents 'ModuleNotFoundError' "
        "or binary C++ linkage mismatch when an operator triggers reconstruction from a standard terminal without activating the venv."
    )
    story.append(make_code_box("reconstruct_dust3r.py", "39-58", "auto_switch_venv()", code_desc_1, styles))
    story.append(Spacer(1, 6))

    story.append(Paragraph("2.2 Environment Safeguards & Apple Silicon Metal Optimization", styles['SectionH2']))
    story.append(Paragraph(
        "Lines 30-33 of <code>reconstruct_dust3r.py</code> configure critical environmental variables before any computational libraries import:", styles['Body']
    ))
    story.append(Paragraph("<b>1. <code>os.environ['OMP_NUM_THREADS'] = '1'</code>:</b> OpenMP multi-threading within native C++ routines (Open3D and PyTorch) causes race conditions and memory deadlocks when competing with GPU/MPS dispatch queues. Restricting CPU parallelism to single-thread per operator ensures strictly deterministic execution and zero deadlocks.", styles['BulletText']))
    story.append(Paragraph("<b>2. <code>os.environ['PYTORCH_ENABLE_MPS_FALLBACK'] = '1'</code>:</b> Apple Silicon uses the Metal Performance Shaders (MPS) framework. Some advanced 3D tensor operations in DUSt3R are not natively implemented in Apple Metal kernels. Setting this flag allows PyTorch to automatically route unsupported GPU ops to the CPU vector unit rather than throwing a fatal runtime exception.", styles['BulletText']))

    algo2_steps = [
        "Query <code>torch.cuda.is_available()</code>. If True, select NVIDIA GPU compute device (<code>device = 'cuda'</code>).",
        "If CUDA is unavailable, query <code>torch.backends.mps.is_available()</code>. If True, select Apple Silicon Metal compute (<code>device = 'mps'</code>).",
        "If both hardware accelerators are absent, default to CPU execution (<code>device = 'cpu'</code>).",
        "Log selected device and allocate operational tensors accordingly."
    ]
    story.append(make_algorithm_box(
        "2", "Hardware Acceleration Device Priority Chain (detect_device)",
        "System hardware state, GPU drivers, PyTorch backend configuration",
        algo2_steps,
        "Optimal device handle string: 'cuda' | 'mps' | 'cpu'",
        styles
    ))
    story.append(Spacer(1, 10))

    # ==================================================================
    # MODULE 3: NEURAL FOUNDATION — DUST3R DEEP-DIVE
    # ==================================================================
    story.append(Paragraph("Module 3: Neural Foundation — DUSt3R Architecture Deep-Dive", styles['SectionH1']))
    story.append(HRFlowable(width="100%", thickness=1, color=BLUE_SECONDARY, spaceBefore=0, spaceAfter=6))

    story.append(Paragraph("3.1 What is DUSt3R and How Does it Discard Classical Constraints?", styles['SectionH2']))
    story.append(Paragraph(
        "DUSt3R stands for <b>Dense and Unconstrained Stereo 3D Reconstruction</b> (developed by Naver Labs Europe). "
        "Unlike all prior 3D reconstruction systems that required camera calibration, focal lengths, SIFT matching, "
        "and epipolar geometry constraints, DUSt3R frames 3D reconstruction as a <b>direct point regression problem</b>. "
        "Given any two uncalibrated images, the neural network directly predicts the 3D coordinate of every single pixel.", styles['Body']
    ))

    story.append(Paragraph("3.2 The Four Core Neural Components of DUSt3R", styles['SectionH2']))
    story.append(Paragraph("<b>Component 1: Patch Tokenization (Vision Transformer Input)</b><br/>"
                           "Standard convolutional networks look at images through small, local receptive fields. "
                           "DUSt3R takes both input images (scaled to 512×512 resolution) and chops them into a grid "
                           "of non-overlapping 16×16 pixel square patches. Each patch is linearly projected into a "
                           "high-dimensional vector (token) containing visual texture, edges, and spatial position embeddings.", styles['Body']))

    story.append(Paragraph("<b>Component 2: Siamese ViT-Large Encoder</b><br/>"
                           "Both tokenized images are fed into a shared Vision Transformer (ViT-Large). "
                           "'Siamese' means the exact same network weights process Image 1 and Image 2 independently. "
                           "The encoder extracts deep semantic features: distinguishing between structural architectural planes "
                           "(floors, walls) and transient foreground objects (furniture, forensic markers).", styles['Body']))

    story.append(Paragraph("<b>Component 3: Cross-Attention Decoder</b><br/>"
                           "This is where the geometric magic occurs. The decoder uses cross-attention layers where tokens from Image 1 "
                           "interrogate tokens from Image 2 as queries, keys, and values. The network explicitly calculates: "
                           "<i>'Where does this patch on the crime scene floor in Image 1 appear when viewed from the camera perspective of Image 2?'</i> "
                           "This mimics human stereoscopic vision, understanding relative 3D disparity without explicit math.", styles['Body']))

    story.append(Paragraph("<b>Component 4: DPT (Dense Prediction Transformer) Regression Heads</b><br/>"
                           "The decoded high-dimensional tokens are upsampled back to full image resolution via DPT heads, "
                           "producing two twin output tensors for each image:", styles['Body']))
    story.append(Paragraph("• <b>Pointmap Tensor (X):</b> An (H × W × 3) matrix where every pixel coordinate (u,v) contains an actual 3-dimensional coordinate (X, Y, Z) expressed in the reference frame of Camera 1.", styles['BulletText']))
    story.append(Paragraph("• <b>Confidence Map Tensor (C):</b> An (H × W) matrix where every pixel contains a scalar value indicating how geometrically confident the neural network is in that 3D point prediction.", styles['BulletText']))

    algo3_steps = [
        "Receive pair of raw RGB images $(I_1, I_2)$ from the scene graph queue.",
        "Resize and normalize images to $512 \\times 512$ with bicubic interpolation.",
        "Pass normalized images through the Siamese ViT Encoder to extract feature tokens.",
        "Execute cross-attention transformer decoding between Image 1 and Image 2 tokens.",
        "DPT heads regress 3D Pointmaps: $X^{1,1}$ (Image 1 points in Camera 1 frame) and $X^{2,1}$ (Image 2 points in Camera 1 frame).",
        "DPT heads regress Confidence Maps: $C^{1,1}$ and $C^{2,1}$.",
        "Return pointmaps and confidence scores to the Global Alignment module."
    ]
    story.append(make_algorithm_box(
        "3", "DUSt3R Neural Pairwise 3D Regression Pipeline",
        "Two uncalibrated 2D RGB images (I1, I2)",
        algo3_steps,
        "Dense 3D pointmaps (X11, X21) and confidence maps (C11, C21)",
        styles
    ))
    story.append(Spacer(1, 6))

    conf_expl = (
        "<b>What Does the Confidence Map Actually Measure?</b> The confidence score $C$ is trained to correlate "
        "with depth certainty. Sky, shiny mirrors, transparent glass windows, and motion-blurred regions receive "
        "extremely low confidence ($C < 1.0$), while textured floorboards, physical evidence markers, and wall corners "
        "receive high confidence ($C > 2.5$). In our code (line 554), we enforce <code>scene.min_conf_thr = 1.5</code>, "
        "which acts as a razor-sharp filter cutting away all ambiguous floating optical hallucinations!"
    )
    story.append(make_callout("WHY CONFIDENCE GATING IS VITAL FOR FORENSICS", conf_expl, LIGHT_BG_PURPLE, BORDER_PURPLE, colors.HexColor("#6B21A8"), styles))
    story.append(Spacer(1, 10))

    # ==================================================================
    # MODULE 4: SCENE GRAPH & PAIR MATCHING STRATEGY
    # ==================================================================
    story.append(Paragraph("Module 4: Scene Graph Construction & Pair Matching Strategy", styles['SectionH1']))
    story.append(HRFlowable(width="100%", thickness=1, color=BLUE_SECONDARY, spaceBefore=0, spaceAfter=6))

    story.append(Paragraph("4.1 The Quadratic Explosion Problem on Edge Devices", styles['SectionH2']))
    story.append(Paragraph(
        "If an investigator captures $N$ photos of a crime scene, evaluating every possible image pair requires "
        "$\\frac{N(N-1)}{2}$ neural network evaluations. For 5 photos, that is only 10 pairs. But for 30 photos, "
        "that is 435 pairs! Running 435 ViT-Large inference passes causes massive thermal throttling and "
        "Out-of-Memory (OOM) crashes on standard laptops. Our pipeline implements a <b>dynamic scene graph</b>:", styles['Body']
    ))

    algo4_steps = [
        "Count total number of input photos $N$.",
        "<b>Branch A (Small Scene, $N \\le 5$):</b> Select <code>scene_graph = 'complete'</code>. Construct all combinations of pairs to maximize baseline overlap.",
        "<b>Branch B (Large Scene, $N > 5$):</b> Select <code>scene_graph = 'swin-3'</code> (Sliding Window with window size 3). Images are paired only with immediate sequential neighbors: $(i, i+1), (i, i+2), (i, i+3)$.",
        "<b>Symmetrize Pairs:</b> Set <code>symmetrize=True</code> so both forward $(i,j)$ and backward $(j,i)$ passes are registered for consistent bidirectional visibility.",
        "Pass filtered pair list to the batched inference queue."
    ]
    story.append(make_algorithm_box(
        "4", "Dynamic Scene Graph Selection & Sliding Window (reconstruct_dust3r.py lines 520-525)",
        "Input photo sequence of length N",
        algo4_steps,
        "Optimized list of image pairs for neural evaluation",
        styles
    ))
    story.append(Spacer(1, 6))

    code_desc_2 = (
        "Lines 520-525: <code>scene_graph = 'complete' if len(images) <= 5 else 'swin-3'</code>. "
        "This is an engineering decision that keeps processing under 60 seconds on Apple Silicon while "
        "guaranteeing continuous topological tracking across the entire room."
    )
    story.append(make_code_box("reconstruct_dust3r.py", "520-525", "make_pairs()", code_desc_2, styles))
    story.append(Spacer(1, 10))

    # ==================================================================
    # MODULE 5: GLOBAL ALIGNMENT & MULTI-VIEW FUSION
    # ==================================================================
    story.append(Paragraph("Module 5: Global Alignment & Multi-View Fusion", styles['SectionH1']))
    story.append(HRFlowable(width="100%", thickness=1, color=BLUE_SECONDARY, spaceBefore=0, spaceAfter=6))

    story.append(Paragraph("5.1 The Local Coordinate Conflict & The Need for Global Alignment", styles['SectionH2']))
    story.append(Paragraph(
        "DUSt3R produces 3D pointmaps for pairs. That means Pair (1,2) produces points in Camera 1's local coordinate frame, "
        "while Pair (2,3) produces points in Camera 2's local coordinate frame! They do not share a common world coordinate space. "
        "To build a single unified crime scene room, we must solve for the exact 3D rigid transformation "
        "(Rotation $R_i$, Translation $t_i$, and Scale $\\sigma_i$) for every camera view simultaneously. "
        "This is performed by <code>GlobalAlignerMode.PointCloudOptimizer</code> (lines 538-552).", styles['Body']
    ))

    algo5_steps = [
        "<b>Minimum Spanning Tree (MST) Initialization:</b> Build a graph where nodes are cameras and edge weights represent pair confidence scores. Compute the MST to find the strongest geometric connectivity and establish initial camera poses.",
        "<b>Parameterization:</b> Assign each camera an unknown rigid transformation in 3D space: $T_i = (R_i, t_i, \\sigma_i) \\in SE(3) \\times \\mathbb{R}^+$.",
        "<b>Objective Loss Function:</b> Define a global loss that penalizes 3D distance between overlapping points predicted across different image pairs, weighted heavily by their neural confidence scores.",
        "<b>Optimization via Gradient Descent:</b> Execute 300 iterations of gradient descent using a Cosine Annealing Learning Rate scheduler. Gradually adjust all camera poses until all point clouds snap into perfect alignment.",
        "<b>Memory Flush:</b> Once alignment completes, immediately delete the heavy neural network from RAM and call <code>torch.mps.empty_cache()</code> or <code>torch.cuda.empty_cache()</code> to free memory for subsequent 3D meshing algorithms."
    ]
    story.append(make_algorithm_box(
        "5", "Global PointCloudOptimizer Multi-View Alignment",
        "Disjoint pairwise pointmaps and confidence scores",
        algo5_steps,
        "Globally consistent unified 3D point cloud and camera pose matrices",
        styles
    ))
    story.append(Spacer(1, 6))

    story.append(Paragraph("5.2 Point Cloud Extraction & Confidence Gating", styles['SectionH2']))
    story.append(Paragraph(
        "In lines 554-573, once global alignment converges, the point cloud is extracted from the scene optimizer:", styles['Body']
    ))
    story.append(Paragraph("1. <code>scene.min_conf_thr = 1.5</code>: All point predictions with confidence $< 1.5$ are masked out.", styles['BulletText']))
    story.append(Paragraph("2. <code>scene.get_pts3d()</code>: Retrieves aligned 3D coordinate arrays from each camera view.", styles['BulletText']))
    story.append(Paragraph("3. <code>scene.get_masks()</code>: Retrieves binary masks of valid, confident pixels.", styles['BulletText']))
    story.append(Paragraph("4. <b>Point Stacking:</b> All masked points and their corresponding RGB pixel colors are flattened and concatenated into a master NumPy array: <code>pts_all</code> of shape $(M \\times 3)$ and <code>col_all</code> of shape $(M \\times 3)$, where $M$ is typically between 500,000 and 2,000,000 confident 3D points.", styles['BulletText']))
    story.append(Spacer(1, 10))

    # ==================================================================
    # MODULE 6: CAMERA POSE ANALYSIS & COORDINATE INVERSION
    # ==================================================================
    story.append(Paragraph("Module 6: Camera Pose Analysis & Coordinate Inversion Detection", styles['SectionH1']))
    story.append(HRFlowable(width="100%", thickness=1, color=BLUE_SECONDARY, spaceBefore=0, spaceAfter=6))

    story.append(Paragraph("6.1 The Coordinate Convention Clash: OpenCV vs Three.js", styles['SectionH2']))
    story.append(Paragraph(
        "A notorious trap in computer vision is the difference between camera coordinate systems:", styles['Body']
    ))
    story.append(Paragraph("• <b>OpenCV / DUSt3R Convention:</b> $+X$ is Right, $+Y$ is Down, $+Z$ is Forward (pointing into the screen).", styles['BulletText']))
    story.append(Paragraph("• <b>OpenGL / Three.js / WebGL Convention:</b> $+X$ is Right, $+Y$ is Up, $+Z$ is Backward (pointing out of the screen).", styles['BulletText']))
    story.append(Paragraph(
        "If a reconstruction is exported directly without analyzing orientation, the entire crime scene room renders "
        "upside-down in the browser (ceiling on the bottom, floor on top). Our pipeline incorporates an automated "
        "<b>Camera World-Up Vector Analysis</b> (lines 600-618) to detect and fix inverted scenes automatically:", styles['Body']
    ))

    algo6_steps = [
        "Extract the $3 \\times 3$ rotation matrix $R_c$ for every reconstructed camera pose.",
        "In OpenCV camera coordinates, the vector pointing 'up' towards the ceiling of the camera is $[0, -1, 0]^T$.",
        "Compute the world-space up vector for each camera: $\\mathbf{v}_{\\text{up}} = R_c \\cdot [0, -1, 0]^T$.",
        "Extract the Y-component of $\\mathbf{v}_{\\text{up}}$ and compute the arithmetic mean across all cameras: $\\bar{Y}_{\\text{up}}$.",
        "<b>Inversion Test:</b> If $\\bar{Y}_{\\text{up}} < 0$, the cameras were pointing upside-down relative to the global coordinate origin.",
        "<b>Corrective Transformation:</b> Apply a 180° rotation around the X-axis: multiply points and normals by $R_X(\\pi) = \\begin{bmatrix} 1 & 0 & 0 \\\\ 0 & -1 & 0 \\\\ 0 & 0 & -1 \\end{bmatrix}$, flipping both Y and Z axes into true upright orientation."
    ]
    story.append(make_algorithm_box(
        "6", "Automated Camera Pose Inversion Detection & Rectification (lines 600-618)",
        "Camera rotation matrices [R_c] from global alignment",
        algo6_steps,
        "Rectified upright point cloud and camera poses",
        styles
    ))
    story.append(Spacer(1, 10))

    # ==================================================================
    # MODULE 7: POINT CLOUD PURIFICATION & DOWNSAMPLING
    # ==================================================================
    story.append(Paragraph("Module 7: Point Cloud Purification & Downsampling", styles['SectionH1']))
    story.append(HRFlowable(width="100%", thickness=1, color=BLUE_SECONDARY, spaceBefore=0, spaceAfter=6))

    story.append(Paragraph("7.1 Preserving the Raw Dense Point Cloud", styles['SectionH2']))
    story.append(Paragraph(
        "In line 200 of <code>reconstruct_dust3r.py</code>, we make a strategic copy: <code>dense_pcd = copy.deepcopy(pcd)</code>. "
        "<b>Why is this done?</b> Downsampling reduces geometric noise and accelerates surface reconstruction, but it permanently "
        "discards photographic color detail. By saving an untouched copy of the raw, dense point cloud in memory, "
        "we can later transfer maximum-resolution photorealistic colors onto the final polygon mesh!", styles['Body']
    ))

    story.append(Paragraph("7.2 Statistical Outlier Removal (SOR)", styles['SectionH2']))
    story.append(Paragraph(
        "Neural networks occasionally predict stray points floating in empty air (hallucinations). "
        "Our pipeline applies <b>Statistical Outlier Removal (SOR)</b> (line 204):", styles['Body']
    ))

    algo7_steps = [
        "For each 3D point $p$ in the point cloud, identify its $k=20$ nearest spatial neighbors using a KD-Tree.",
        "Calculate the mean distance $d_p$ from point $p$ to all its 20 neighbors.",
        "Compute the global mean $\\mu$ and standard deviation $\\sigma$ of these neighbor distances across the entire scene.",
        "Set the rejection distance threshold: $T = \\mu + (2.0 \\times \\sigma)$.",
        "If a point's local mean distance $d_p > T$, classify it as an isolated noise point and purge it from the cloud."
    ]
    story.append(make_algorithm_box(
        "7", "Statistical Outlier Removal (SOR Filter)",
        "Raw point cloud with potential optical noise",
        algo7_steps,
        "Cleaned point cloud free of isolated floating points",
        styles
    ))
    story.append(Spacer(1, 6))

    story.append(Paragraph("7.3 Adaptive Voxel Downsampling", styles['SectionH2']))
    story.append(Paragraph(
        "A point cloud with 2,000,000 points contains redundant points on flat surfaces. "
        "Instead of hardcoding a fixed voxel size (which breaks if a crime scene is a tiny closet or a huge warehouse), "
        "we calculate an <b>adaptive voxel grid size</b> based on the scene's physical dimensions (lines 207-212):", styles['Body']
    ))
    story.append(Paragraph("• <b>Bounding Box Diagonal:</b> Compute the 3D bounding box diagonal of the scene: $D = \\|\\mathbf{max} - \\mathbf{min}\\|_2$.", styles['BulletText']))
    story.append(Paragraph("• <b>Dynamic Voxel Formula:</b> <code>voxel_size = max(0.008, diag / 250.0)</code>.", styles['BulletText']))
    story.append(Paragraph("• <b>Centroid Binning:</b> The 3D space is divided into cubic voxels of size <code>voxel_size</code>. All points falling within a single cube are replaced by their single geometric centroid. This guarantees uniform point density across all areas of the crime scene without losing fine structural edges.", styles['BulletText']))
    story.append(Spacer(1, 10))

    # ==================================================================
    # MODULE 8: SURFACE NORMAL ESTIMATION & ORIENTATION
    # ==================================================================
    story.append(Paragraph("Module 8: Differential Geometry & Surface Normal Estimation", styles['SectionH1']))
    story.append(HRFlowable(width="100%", thickness=1, color=BLUE_SECONDARY, spaceBefore=0, spaceAfter=6))

    story.append(Paragraph("8.1 What is a Surface Normal and Why Does Meshing Require It?", styles['SectionH2']))
    story.append(Paragraph(
        "A point cloud is merely a collection of disconnected dots in space; it has no concept of 'inside' or 'outside', "
        "and no concept of a solid surface. A <b>surface normal</b> $\\mathbf{n}$ is a unit vector perpendicular to the "
        "tangent plane of the surface at that specific point. It indicates which direction the surface is facing. "
        "Without accurate normals, surface reconstruction algorithms (like Poisson) cannot build a solid mesh.", styles['Body']
    ))

    algo8_steps = [
        "<b>Neighborhood Search:</b> For each point $p$, find its 30 nearest neighbors within a search radius $r = 3 \\times \\text{voxel\\_size}$ using Open3D's <code>KDTreeSearchParamHybrid</code>.",
        "<b>Covariance Analysis (PCA):</b> Calculate the $3 \\times 3$ spatial covariance matrix $C$ of these 30 neighbor points.",
        "<b>Eigenvalue Decomposition:</b> Compute the three eigenvectors and eigenvalues of $C$. The eigenvector corresponding to the <b>smallest eigenvalue</b> represents the direction of least variance — which is exactly the surface normal vector $\\mathbf{n}$!",
        "<b>The Ambiguity Problem:</b> Eigenvectors have a sign ambiguity (a vector $\\mathbf{n}$ and $-\\mathbf{n}$ are both valid solutions). One point might point outward while its neighbor points inward, creating chaotic holes.",
        "<b>Riemannian Minimum Spanning Tree (MST) Orientation:</b> Call <code>pcd.orient_normals_consistent_tangent_plane(k=30)</code>. Build a Riemannian graph over the point cloud and propagate consistent vector orientations so all normals point coherently outward away from the room interior."
    ]
    story.append(make_algorithm_box(
        "8", "PCA Surface Normal Estimation & Riemannian MST Orientation (lines 217-224)",
        "Downsampled point cloud",
        algo8_steps,
        "Point cloud with globally consistent outward-pointing normal vectors",
        styles
    ))
    story.append(Spacer(1, 10))

    # ==================================================================
    # MODULE 9: SCREENED POISSON SURFACE RECONSTRUCTION
    # ==================================================================
    story.append(Paragraph("Module 9: Surface Reconstruction — Screened Poisson & Fallbacks", styles['SectionH1']))
    story.append(HRFlowable(width="100%", thickness=1, color=BLUE_SECONDARY, spaceBefore=0, spaceAfter=6))

    story.append(Paragraph("9.1 The Mathematical Principle of Screened Poisson", styles['SectionH2']))
    story.append(Paragraph(
        "Developed by Kazhdan and Hoppe, <b>Screened Poisson Surface Reconstruction</b> treats 3D meshing as an "
        "implicit spatial function problem. Instead of trying to connect points directly with lines, it defines an "
        "<b>Indicator Function $\\chi$</b> over the entire 3D space: $\\chi = 1$ inside the room walls/objects, "
        "and $\\chi = 0$ outside in empty air. The boundary where $\\chi$ shifts from 0 to 1 is the exact crime scene surface! "
        "The gradient of this function $\\nabla \\chi$ must match our estimated surface normals $\\mathbf{V}$. "
        "This leads to the Poisson Partial Differential Equation: $\\nabla^2 \\chi = \\nabla \\cdot \\mathbf{V}$.", styles['Body']
    ))

    story.append(Paragraph("9.2 Why Octree Depth 9 is the Golden Standard for Forensics", styles['SectionH2']))
    story.append(Paragraph(
        "The Poisson algorithm subdivides the 3D bounding box into an adaptive hierarchical grid called an <b>Octree</b>. "
        "The <code>depth</code> parameter controls how many times space is recursively divided:", styles['Body']
    ))
    story.append(Paragraph("• <b>Depth 7 ($2^7 = 128$ cells per axis):</b> Coarse, rounded corners, forensic evidence markers blur into blobs.", styles['BulletText']))
    story.append(Paragraph("• <b>Depth 8 ($2^8 = 256$ cells per axis):</b> Acceptable for architecture, but fine blood spatter trails and shell casings lose definition.", styles['BulletText']))
    story.append(Paragraph("• <b>Depth 9 ($2^9 = 512$ cells per axis):</b> Provides millimeter-scale resolution ($~2\\text{mm}-5\\text{mm}$ voxel cells), preserving knife gouges, bullet impacts, and sharp furniture corners while operating safely within 16GB RAM limits.", styles['BulletText']))

    story.append(Paragraph("9.3 Crash Prevention Safeguards in reconstruct_dust3r.py (lines 235-242)", styles['SectionH2']))
    story.append(Paragraph(
        "In our production code, <code>create_from_point_cloud_poisson()</code> is called with strict production safeguards:", styles['Body']
    ))
    story.append(Paragraph("<b>1. <code>n_threads = 1</code>:</b> Open3D's multi-threaded Poisson solver uses OpenMP, which deadlocks and crashes on macOS Metal backends when competing with Python worker pools. Single-threading guarantees 100% crash immunity.", styles['BulletText']))
    story.append(Paragraph("<b>2. <code>linear_fit = False</code>:</b> Disabling linear fit enforces quadratic B-spline interpolation, producing smooth, continuous wall planes without faceted polygon banding.", styles['BulletText']))

    algo9_steps = [
        "<b>Stage 1 (Primary Target):</b> Attempt Screened Poisson reconstruction at <code>depth = 9</code> with <code>n_threads = 1</code>.",
        "<b>Stage 2 (Memory Fallback):</b> If Depth 9 triggers an Out-of-Memory (OOM) exception, catch the error and retry at <code>depth = 8</code>.",
        "<b>Stage 3 (Low-End Hardware Fallback):</b> If Depth 8 fails, catch the error and retry at <code>depth = 7</code>.",
        "<b>Stage 4 (Emergency Fallback — Ball Pivoting):</b> If all Poisson passes fail, invoke the <b>Ball Pivoting Algorithm (BPA)</b>: <code>create_from_point_cloud_ball_pivoting()</code> using ball radii $[1.5, 3.0, 6.0] \\times \\text{voxel\\_size}$. Imagine rolling a virtual ball over the point cloud — whenever the ball touches three points without falling through, a triangle is formed.",
        "<b>Density Trimming:</b> Poisson reconstruction is a watertight solver: it closes open doorways and windows by generating large 'melted bubble' artifacts where no points exist. We compute the 5th percentile of vertex density and trim away all low-density vertices (line 255): <code>vertices_to_remove = densities < np.percentile(densities, 5)</code>."
    ]
    story.append(make_algorithm_box(
        "9", "Multi-Tier Resilient Surface Reconstruction Ladder (lines 230-265)",
        "Oriented point cloud with normal vectors",
        algo9_steps,
        "Clean, watertight triangular mesh with bubble artifacts removed",
        styles
    ))
    story.append(Spacer(1, 10))

    # ==================================================================
    # MODULE 10: MESH TOPOLOGY PURIFICATION
    # ==================================================================
    story.append(Paragraph("Module 10: Mesh Topology Purification & Degenerate Face Pruning", styles['SectionH1']))
    story.append(HRFlowable(width="100%", thickness=1, color=BLUE_SECONDARY, spaceBefore=0, spaceAfter=6))

    story.append(Paragraph("10.1 Eliminating Geometric Degeneracy", styles['SectionH2']))
    story.append(Paragraph(
        "Raw output meshes from Poisson solvers frequently contain topological anomalies that break 3D rendering engines "
        "and physics simulators (e.g., bullet trajectory raycasters in our Crime Recreation Studio). "
        "In lines 270-285 of <code>reconstruct_dust3r.py</code>, we execute automated topology repairs:", styles['Body']
    ))
    story.append(Paragraph("• <b>Degenerate Triangle Pruning:</b> Triangles with zero surface area (where all 3 vertices are collinear) cause division-by-zero errors in ray-intersection tests. Removed via <code>mesh.remove_degenerate_triangles()</code>.", styles['BulletText']))
    story.append(Paragraph("• <b>Duplicate Vertex Welding:</b> Vertices occupying the exact same 3D coordinate are unified via <code>mesh.remove_duplicated_vertices()</code>.", styles['BulletText']))
    story.append(Paragraph("• <b>Non-Manifold Edge Pruning:</b> An edge shared by 3 or more triangles violates physical reality (a wall cannot split into 3 directions at a single seam). Cleaned via <code>mesh.remove_non_manifold_edges()</code>.", styles['BulletText']))
    story.append(Spacer(1, 10))

    # ==================================================================
    # MODULE 11: HIGH-FIDELITY KDTREE COLOR TRANSFER
    # ==================================================================
    story.append(Paragraph("Module 11: High-Fidelity KDTree Color Transfer", styles['SectionH1']))
    story.append(HRFlowable(width="100%", thickness=1, color=BLUE_SECONDARY, spaceBefore=0, spaceAfter=6))

    story.append(Paragraph("11.1 The Failure of Classical UV Texture Mapping on Volumetric Scans", styles['SectionH2']))
    story.append(Paragraph(
        "In standard 3D graphics (like video game assets), models use 2D UV texture maps. However, for raw scanned "
        "crime scenes containing complex furniture, blood stains, and broken glass, generating 2D UV unwraps creates "
        "severe seam tearing, texture stretching, and projection distortions. Furthermore, Poisson reconstruction "
        "interpolates new vertices that possess zero color information (rendering the room solid gray).", styles['Body']
    ))

    algo10_steps = [
        "Retrieve the untouched, high-resolution <code>dense_pcd</code> preserved prior to downsampling.",
        "Construct a 3D K-Dimensional Spatial Tree (<b>KD-Tree</b>) from the dense point cloud coordinates using <code>scipy.spatial.cKDTree</code> or Open3D's KDTreeSearchParam.",
        "For each vertex $v$ in the newly generated Poisson mesh, query the KD-Tree for its single nearest 3D neighbor ($k=1$) in the dense point cloud.",
        "Copy the original photographic sRGB color from the nearest neighbor point directly onto vertex $v$.",
        "Append an alpha transparency channel (set to $255$ for full opacity) to format the colors as standard 4-channel RGBA floats, ready for WebGL GPU shaders."
    ]
    story.append(make_algorithm_box(
        "10", "KD-Tree Vertex Color Projection Pipeline (lines 288-300)",
        "Uncolored Poisson mesh and original raw dense point cloud",
        algo10_steps,
        "Photorealistically colored vertex-painted 3D mesh",
        styles
    ))
    story.append(Spacer(1, 6))

    kdtree_perf = (
        "<b>Computational Complexity of KD-Tree:</b> Building the KD-Tree takes $\\mathcal{O}(M \\log M)$ time, "
        "and querying each of the $V$ mesh vertices takes only $\\mathcal{O}(\\log M)$ time. For 1,000,000 points, "
        "this transfers photorealistic color across the entire room in under 1.8 seconds on a standard laptop!"
    )
    story.append(make_callout("ALGORITHMIC EFFICIENCY NOTE", kdtree_perf, LIGHT_BG_GREEN, BORDER_GREEN, colors.HexColor("#065F46"), styles))
    story.append(Spacer(1, 10))

    # ==================================================================
    # MODULE 12: ROOM ALIGNMENT, BOUNDING & SCENE EXPORT
    # ==================================================================
    story.append(Paragraph("Module 12: Room Alignment, Bounding & Scene Export", styles['SectionH1']))
    story.append(HRFlowable(width="100%", thickness=1, color=BLUE_SECONDARY, spaceBefore=0, spaceAfter=6))

    story.append(Paragraph("12.1 Spatial Normalization & PCA Yaw Rectification (align_and_export_room)", styles['SectionH2']))
    story.append(Paragraph(
        "Even when upright, the reconstructed room might be floating miles away from the origin $(0,0,0)$ or rotated "
        "at an awkward 37° diagonal angle. In <code>reconstruct_dust3r.py</code> lines 308-379, <code>align_and_export_room()</code> "
        "implements three mathematical normalization operations:", styles['Body']
    ))

    algo11_steps = [
        "<b>Median Centering:</b> Compute the spatial median of all vertex coordinates: $\\mathbf{m} = \\text{median}(V)$. Translate the entire mesh by $-\\mathbf{m}$ so the center of the crime scene rests precisely at world origin $(0,0,0)$. <i>(Why median instead of mean? Median is mathematically immune to stray outlier points that would skew the center!)</i>",
        "<b>PCA Planar Yaw Alignment:</b> Project all vertex coordinates onto the horizontal ground plane $(X, Z)$. Compute the $2 \\times 2$ planar covariance matrix. The dominant eigenvector reveals the primary orientation of the room's longest walls. Calculate the yaw angle $\\theta = \\text{atan2}(v_z, v_x)$ and rotate the mesh around the Y-axis by $-\\theta$, snapping dominant walls parallel to the $X$ and $Z$ axes.",
        "<b>Bounding Box Normalization:</b> Compute the maximum spatial extent $E = \\max(X_{\\max}-X_{\\min}, Y_{\\max}-Y_{\\min}, Z_{\\max}-Z_{\\min})$. Uniformly scale the mesh: $V_{\\text{scaled}} = V \\times (10.0 / E)$, normalizing the entire room to fit within a standard 10-unit interactive viewer viewport."
    ]
    story.append(make_algorithm_box(
        "11", "Spatial Normalization, Centering & PCA Yaw Alignment",
        "Uncalibrated raw Poisson mesh",
        algo11_steps,
        "Origin-centered, wall-aligned, normalized 3D mesh",
        styles
    ))
    story.append(Spacer(1, 6))

    story.append(Paragraph("12.2 Stage Depth Markers & room_bounds.json", styles['SectionH2']))
    story.append(Paragraph(
        "The web-based Crime Recreation Studio needs to know the physical boundaries of the room to configure collision "
        "boundaries, camera frustum clipping, and navigation grid floor tiles. In lines 365-375, the pipeline writes <code>room_bounds.json</code>:", styles['Body']
    ))
    story.append(Paragraph("• <code>minX, maxX, minY, maxY, minZ, maxZ</code>: Exact spatial bounding coordinates.", styles['BulletText']))
    story.append(Paragraph("• <code>F: 5.5</code>: A hardcoded <b>Stage Depth Marker</b>. This parameter informs the Three.js camera controller where the focal 'action stage' of the crime scene is located, guaranteeing the investigator spawns at the optimal viewing distance upon opening the file.", styles['BulletText']))

    story.append(Paragraph("12.3 Multi-Target GLB Export & Synchronization", styles['SectionH2']))
    story.append(Paragraph(
        "In <code>export_glb()</code> (lines 382-467), the mesh is serialized into <b>Binary glTF (.glb)</b> format. "
        "GLB is the web industry standard for 3D assets because it packages geometry, vertex colors, and materials "
        "into a single compact binary file that loads instantly in Three.js without external texture dependencies. "
        "The pipeline saves the GLB and automatically copies it across three project locations:", styles['Body']
    ))
    story.append(Paragraph("1. <code>output/scene.glb</code>: The permanent archival copy.", styles['BulletText']))
    story.append(Paragraph("2. <code>frontend/public/models/scene.glb</code>: Used by the Vite development server.", styles['BulletText']))
    story.append(Paragraph("3. <code>frontend/dist/models/scene.glb</code>: Used by the production compiled web bundle.", styles['BulletText']))
    story.append(Spacer(1, 10))

    # ==================================================================
    # MODULE 13: ADVANCED MESH ENHANCEMENT ENGINE
    # ==================================================================
    story.append(Paragraph("Module 13: Advanced Post-Processing Engine (enhance_mesh.py)", styles['SectionH1']))
    story.append(HRFlowable(width="100%", thickness=1, color=BLUE_SECONDARY, spaceBefore=0, spaceAfter=6))

    story.append(Paragraph("13.1 The 8-Step Mesh Refinement Pipeline", styles['SectionH2']))
    story.append(Paragraph(
        "While <code>reconstruct_dust3r.py</code> generates the initial 3D mesh, the dedicated enhancement module "
        "<code>scripts/enhance_mesh.py</code> runs an advanced 8-stage post-processing pipeline designed to bring "
        "the reconstructed crime scene to forensic grade:", styles['Body']
    ))

    story.append(Paragraph("<b>Step 1: Texture Void Inpainting via Euclidean Distance Transform (EDT)</b><br/>"
                           "When Poisson reconstruction closes gaps, UV texture regions may have black holes or missing texels. "
                           "The function <code>inpaint_texture_array()</code> (lines 37-77) uses <code>scipy.ndimage.distance_transform_edt</code>. "
                           "For every uncolored pixel, EDT calculates the shortest spatial distance to the nearest valid colored pixel "
                           "and copies its exact RGB value, smoothly inpainting texture gaps without blurring sharp evidence edges.", styles['Body']))

    story.append(Paragraph("<b>Step 2: Stretched Needle-Face Pruning</b><br/>"
                           "Poisson solvers occasionally bridge distant room fixtures by generating long, skinny 'needle triangles'. "
                           "In lines 151-175, the code calculates the edge lengths of all triangles. Any triangle with an edge length exceeding "
                           "an adaptive threshold ($\\text{mean} + 3.0 \\times \\text{std}$) is instantly pruned.", styles['Body']))

    story.append(Paragraph("<b>Step 3: Connected Component Graph Filtering (Shard Pruning)</b><br/>"
                           "Small floating clusters of polygons ('islands' or 'shards') often hover in the air due to window reflections. "
                           "In lines 180-205, the mesh topology is converted into an adjacency graph using <code>scipy.sparse.csgraph.connected_components</code>. "
                           "The algorithm identifies all isolated sub-meshes, measures their vertex counts, and permanently discards any component "
                           "smaller than 10% of the main crime scene room.", styles['Body']))

    story.append(Paragraph("<b>Step 4: Normal Voting Y-Axis Flip</b><br/>"
                           "In lines 215-235, the code collects the vertical component ($n_y$) of all upward and downward facing surface normals. "
                           "If the majority of flat surface normals point towards negative Y, the mesh is inverted. A 180° rotation matrix "
                           "is applied to restore proper upright orientation.", styles['Body']))

    story.append(Paragraph("<b>Step 5: Cardinal Wall Yaw Alignment via Normal Azimuth Histogram</b><br/>"
                           "Human architecture is dominated by perpendicular walls (Manhattan World assumption). "
                           "In lines 240-270, the algorithm computes the azimuth angle $\\theta = \\text{atan2}(n_x, n_z)$ of all vertical wall normals. "
                           "It bins these angles into a histogram modulo 90° ($[0^\\circ, 90^\\circ)$). The peak of this histogram identifies "
                           "the true rotational bias of the walls. The scene is rotated by the negative of this angle, ensuring room walls "
                           "align perfectly with the grid axes of the Three.js Crime Recreation Studio.", styles['Body']))

    story.append(Paragraph("<b>Step 6: Least-Squares Floor Plane Fitting</b><br/>"
                           "To ensure furniture and avatars do not tilt on a crooked floor, lines 275-295 isolate the lowest 20% of vertices "
                           "in the room. A mathematical plane equation $Y = aX + bZ + c$ is fitted to these floor points using linear least-squares "
                           "(<code>np.linalg.lstsq</code>). The surface normal of this fitted floor plane is computed, and a corrective 3D rotation "
                           "is applied so the floor becomes perfectly horizontal.", styles['Body']))

    story.append(Paragraph("<b>Step 7: Floor Grounding & Origin Centering</b><br/>"
                           "Once leveled, the minimum Y-coordinate of the floor is measured, and the entire mesh is translated vertically "
                           "so that the floor sits exactly at $Y = 0.0$. The horizontal center of the floor is placed at $(X=0, Z=0)$.", styles['Body']))

    story.append(Paragraph("<b>Step 8: Metric Normalization to Standard Forensic Room Height</b><br/>"
                           "Cameras do not record absolute scale: a photo of a dollhouse looks identical to a photo of a mansion! "
                           "To establish a realistic metric scale without physical tape measures, lines 315-325 compute the 95th percentile "
                           "height (the ceiling height). In residential architecture, standard ceiling height is <b>3.2 meters</b>. "
                           "The mesh is scaled by $S = 3.2 / (Y_{\\text{ceiling}} - Y_{\\text{floor}})$. Now, 1.0 unit in Three.js equals "
                           "exactly 1.0 real-world meter, allowing realistic ballistics and spatial measurements!", styles['Body']))
    story.append(Spacer(1, 10))

    # ==================================================================
    # MODULE 14: CARDINAL DIRECTION & COMPASS CALIBRATION
    # ==================================================================
    story.append(Paragraph("Module 14: Cardinal Direction & Compass Calibration (calibrate_direction.py)", styles['SectionH1']))
    story.append(HRFlowable(width="100%", thickness=1, color=BLUE_SECONDARY, spaceBefore=0, spaceAfter=6))

    story.append(Paragraph("14.1 Forensic Geographic North Alignment", styles['SectionH2']))
    story.append(Paragraph(
        "In forensic death investigations, sunlight angles, shadow lengths, and compass headings (e.g., 'the suspect "
        "fled through the North-facing window') are legally critical. A virtual 3D mesh has no intrinsic knowledge of "
        "where geographic North is located. The script <code>scripts/calibrate_direction.py</code> solves this:", styles['Body']
    ))

    algo12_steps = [
        "The investigator specifies a reference photo index (e.g., photo #0) and the known real-world compass heading the camera was facing when that photo was taken (e.g., $90^\\circ$ East).",
        "Load <code>camera_poses.json</code> generated during global reconstruction alignment. Extract the $3 \\times 3$ camera rotation matrix $R$.",
        "Compute the forward optical vector of the camera in 3D world space: $\\mathbf{v}_{\\text{fwd}} = R \\cdot [0, 0, 1]^T$.",
        "Compute the camera's azimuth angle on the horizontal ground plane: $\\theta_{\\text{cam}} = \\text{atan2}(v_x, -v_z) \\times \\frac{180}{\\pi}$.",
        "Calculate the global North Offset angle: $\\text{northOffset} = (\\theta_{\\text{cam}} - \\theta_{\\text{target}} + 360) \\pmod{360}$.",
        "Save offset to <code>output/direction.json</code>. The Three.js frontend reads this file to rotate its interactive 3D Compass Rose HUD, ensuring virtual North matches real-world geographic North!"
    ]
    story.append(make_algorithm_box(
        "12", "Real-World Geographic Compass Calibration Pipeline",
        "Camera rotation matrix R and user-specified reference heading",
        algo12_steps,
        "Calibrated northOffset angle stored in direction.json",
        styles
    ))
    story.append(Spacer(1, 10))

    # ==================================================================
    # MODULE 15: DYNAMIC SCENE OBJECTS & NAVIGATION GRID GENERATION
    # ==================================================================
    story.append(Paragraph("Module 15: Dynamic 3D Scene Objects, Entrances & Navigation Grid (detect_scene_objects.py)", styles['SectionH1']))
    story.append(HRFlowable(width="100%", thickness=1, color=BLUE_SECONDARY, spaceBefore=0, spaceAfter=6))

    story.append(Paragraph("15.1 The Bridge Between 3D Meshing and AI Crime Simulation", styles['SectionH2']))
    story.append(Paragraph(
        "A 3D model alone cannot support autonomous pathfinding: if an AI investigator or criminal avatar attempts "
        "to walk through the virtual room, it will clip through solid tables, chairs, and brick walls! "
        "The dedicated script <code>scripts/detect_scene_objects.py</code> analyzes the reconstructed 3D mesh geometry "
        "and rasterizes an intelligent 2D <b>Navigation Obstacle Grid</b> (<code>output/navgrid.json</code>) "
        "and detects physical boundaries and room entrances (<code>output/boundary_markers.json</code>):", styles['Body']
    ))

    algo13_steps = [
        "<b>Wall Surface Histogramming:</b> Slice mesh vertices between $Y = \\text{floor} + 0.40\\text{m}$ and $Y = \\text{floor} + 1.80\\text{m}$ (human eye-level wall band). Bin the $X$ and $Z$ coordinates into 5cm histogram bins to automatically locate the physical peaks of East, West, North, and South walls.",
        "<b>Boundary Markers Calculation:</b> Compute the 8 cardinal sector coordinates (NW, NE, SE, SW, N, E, S, W). If wall vertex count is sparse, execute an Oriented Bounding Box (OBB) covariance analysis rotated by <code>northOffset</code>.",
        "<b>Dense Surface Sampling:</b> Uniformly sample 150,000 to 350,000 spatial points across the 3D mesh surface using <code>trimesh.sample.sample_surface()</code>.",
        "<b>2D NavGrid Rasterization:</b> Construct a 2D grid with 0.12m cell resolution (12 cm cells). For each cell $(X, Z)$, fit a local least-squares floor plane equation $Y = aX + bZ + c$.",
        "<b>Walkable Floor vs Obstacle Classification:</b> Surface points within 8cm of local floor with upward normals are classified as walkable floor. Any points rising $> 12\\text{cm}$ above local floor up to $1.80\\text{m}$ (tables, chairs, beds, clutter) are classified as <b>physical obstacles</b>.",
        "<b>Obstacle Dilations & Bounds Gating:</b> Apply morphological binary dilation (<code>scipy.ndimage.binary_dilation</code>) with a 1-cell radius (0.12m) to enforce human body clearance around furniture. Perform ray-casting point-in-polygon tests to mark all regions outside room walls as impassable.",
        "<b>Output Serialization:</b> Save the complete traversability matrix, cell dimensions, and boundary markers to <code>output/navgrid.json</code> and <code>output/boundary_markers.json</code> for Three.js A* pathfinding."
    ]
    story.append(make_algorithm_box(
        "13", "Dynamic 3D Mesh Obstacle Rasterization & NavGrid Generation",
        "Reconstructed 3D GLB mesh and northOffset",
        algo13_steps,
        "Walkable 2D A* navigation grid (navgrid.json) and room boundaries",
        styles
    ))
    story.append(Spacer(1, 10))

    # ==================================================================
    # MODULE 16: MANUAL REMEDIATION & MULTI-TARGET SYNC
    # ==================================================================
    story.append(Paragraph("Module 16: Manual Remediation & Multi-Target Synchronization (flip_glb.py)", styles['SectionH1']))
    story.append(HRFlowable(width="100%", thickness=1, color=BLUE_SECONDARY, spaceBefore=0, spaceAfter=6))

    story.append(Paragraph("16.1 The 1-Click Operational Remediation Tool", styles['SectionH2']))
    story.append(Paragraph(
        "In production forensic field operations, if an unusual camera trajectory causes a reconstructed scene "
        "to load upside-down or reversed, an investigator cannot afford to wait 5 minutes re-running the entire neural pipeline. "
        "The utility <code>flip_glb.py</code> provides instant, zero-recomputation remediation:", styles['Body']
    ))

    algo14_steps = [
        "Load existing reconstructed model <code>output/scene_textured.glb</code> via <code>trimesh.load(process=False)</code>.",
        "Construct a 180° rotation matrix around the X-axis: <code>trimesh.transformations.rotation_matrix(math.pi, [1, 0, 0])</code>.",
        "Apply the matrix transformation to all mesh vertices and surface normals in place.",
        "Re-export the flipped GLB to <code>output/scene_textured.glb</code>.",
        "Instantly synchronize the modified GLB file to both <code>frontend/public/models</code> and <code>frontend/dist/models</code>.",
        "Automatically trigger subprocess re-execution of <code>calibrate_direction.py</code> and <code>detect_scene_objects.py</code> to recalculate the compass heading and navigation grid for the newly flipped orientation."
    ]
    story.append(make_algorithm_box(
        "14", "One-Click Inversion Remediation & Hot-Reload Pipeline (flip_glb.py)",
        "Inverted GLB model on disk",
        algo14_steps,
        "Rectified upright GLB synchronized to frontend with updated NavGrid",
        styles
    ))
    story.append(Spacer(1, 10))

    # ==================================================================
    # MODULE 17: ORCHESTRATION & REAL-TIME SSE STREAMING
    # ==================================================================
    story.append(Paragraph("Module 17: Asynchronous Orchestration & Real-Time SSE Streaming", styles['SectionH1']))
    story.append(HRFlowable(width="100%", thickness=1, color=BLUE_SECONDARY, spaceBefore=0, spaceAfter=6))

    story.append(Paragraph("17.1 Node.js Subprocess Management & Server-Sent Events (server.js)", styles['SectionH2']))
    story.append(Paragraph(
        "Neural 3D reconstruction is computationally intensive, taking between 20 to 90 seconds. "
        "In a web environment, standard HTTP requests time out after 30 seconds. In <code>server.js</code>, "
        "the reconstruction endpoint <code>/api/reconstruct</code> uses <b>Server-Sent Events (SSE)</b> "
        "(<code>text/event-stream</code>) to maintain a continuous, live diagnostic feed between the Python "
        "backend and the investigator's web browser:", styles['Body']
    ))

    sse_headers = [Paragraph("<b>Pipeline Stage Log Message</b>", styles['TableHeader']),
                   Paragraph("<b>Progress %</b>", styles['TableHeader']),
                   Paragraph("<b>Underlying Computational Action</b>", styles['TableHeader'])]
    sse_rows = [
        [
            Paragraph("<code>Detecting hardware accelerator...</code>", styles['TableCell']),
            Paragraph("<b>5%</b>", styles['TableCellBold']),
            Paragraph("Evaluating CUDA vs Apple Silicon MPS vs CPU fallback.", styles['TableCell'])
        ],
        [
            Paragraph("<code>Loading DUSt3R ViT-Large weights...</code>", styles['TableCell']),
            Paragraph("<b>15%</b>", styles['TableCellBold']),
            Paragraph("Loading pre-trained 512MB model tensors into memory.", styles['TableCell'])
        ],
        [
            Paragraph("<code>Constructing scene graph pairs...</code>", styles['TableCell']),
            Paragraph("<b>25%</b>", styles['TableCellBold']),
            Paragraph("Evaluating photo count; configuring complete or swin-3 sliding window.", styles['TableCell'])
        ],
        [
            Paragraph("<code>Executing neural pairwise inference...</code>", styles['TableCell']),
            Paragraph("<b>45%</b>", styles['TableCellBold']),
            Paragraph("Feed-forward passes predicting 3D pointmaps and confidence tensors.", styles['TableCell'])
        ],
        [
            Paragraph("<code>Running Global PointCloudOptimizer...</code>", styles['TableCell']),
            Paragraph("<b>65%</b>", styles['TableCellBold']),
            Paragraph("MST pose initialization and 300 iterations of gradient descent.", styles['TableCell'])
        ],
        [
            Paragraph("<code>Statistical Outlier & Voxel Filtering...</code>", styles['TableCell']),
            Paragraph("<b>75%</b>", styles['TableCellBold']),
            Paragraph("Purging floating noise and computing dynamic voxel centroid grid.", styles['TableCell'])
        ],
        [
            Paragraph("<code>Screened Poisson Surface Reconstruction...</code>", styles['TableCell']),
            Paragraph("<b>85%</b>", styles['TableCellBold']),
            Paragraph("Solving octree depth 9 Poisson PDE and trimming bubble density.", styles['TableCell'])
        ],
        [
            Paragraph("<code>KDTree Color Transfer & GLB Export...</code>", styles['TableCell']),
            Paragraph("<b>95%</b>", styles['TableCellBold']),
            Paragraph("Nearest-neighbor color projection and binary glTF serialization.", styles['TableCell'])
        ],
        [
            Paragraph("<code>RECONSTRUCTION_COMPLETE</code>", styles['TableCell']),
            Paragraph("<b>100%</b>", styles['TableCellBold']),
            Paragraph("Frontend automatically loads 3D scene into Three.js canvas.", styles['TableCell'])
        ]
    ]
    sse_table = Table([sse_headers] + sse_rows, colWidths=[150, 70, 320])
    sse_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), TABLE_HEADER_BG),
        ('GRID', (0,0), (-1,-1), 0.5, RULE_COLOR),
        ('TOPPADDING', (0,0), (-1,-1), 3),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
    ]))
    story.append(sse_table)
    story.append(Spacer(1, 10))

    # ==================================================================
    # MODULE 18: MASTER VIVA ORAL DEFENSE GUIDE (35 QUESTIONS)
    # ==================================================================
    story.append(PageBreak())
    story.append(Paragraph("Module 18: Master Viva & Oral Defense Examination Guide", styles['SectionH1']))
    story.append(HRFlowable(width="100%", thickness=1, color=BLUE_SECONDARY, spaceBefore=0, spaceAfter=6))
    story.append(Paragraph(
        "This section prepares you for tough questions from external examiners, university professors, and forensic "
        "advisory committees. The 35 questions are categorized across six core technical domains with concise model answers:", styles['Body']
    ))
    story.append(Spacer(1, 6))

    # Category A
    story.append(Paragraph("Category A: High-Level Concepts & Forensic Admissibility", styles['SectionH2']))
    story.append(make_viva_box(
        "1", "Why is 3D reconstruction legally superior to standard 2D crime scene photography in a court of law?",
        "Standard 2D photographs suffer from perspective distortion, lack spatial metricity, and cannot verify distances once physical evidence is cleared. A calibrated 3D Digital Twin preserves millimeter-scale spatial relationships, enabling accurate bullet trajectory analysis, blood spatter angle calculations, and virtual witness line-of-sight verifications that comply with evidentiary standards.",
        "Testing understanding of the core forensic motivation and legal value.",
        styles
    ))
    story.append(Spacer(1, 5))

    story.append(make_viva_box(
        "2", "What is the difference between Structure-from-Motion (SfM) and Multi-View Stereo (MVS)?",
        "Structure-from-Motion (SfM) is the first phase: it matches sparse 2D keypoints across images to estimate camera poses and reconstruct a sparse 3D point cloud. Multi-View Stereo (MVS) is the second phase: taking those known camera poses, it computes dense depth maps for every pixel to produce a dense, photorealistic point cloud or surface mesh.",
        "Checking fundamental photogrammetry taxonomy.",
        styles
    ))
    story.append(Spacer(1, 5))

    story.append(make_viva_box(
        "3", "Why does classical SIFT/COLMAP fail on crime scene drywall and blood pools?",
        "Classical SIFT relies on high-contrast local luminance gradients (corners, textured patterns) to compute 128-dimensional descriptors. Featureless surfaces like painted drywall or tile floors lack these gradients, yielding zero matched points. Liquid blood pools and glass create specular reflections that move with the camera, producing false matches and floating geometric noise.",
        "Testing awareness of the limitations of older technology.",
        styles
    ))
    story.append(Spacer(1, 5))

    story.append(make_viva_box(
        "4", "What is the fundamental paradigm shift introduced by DUSt3R over classical SfM?",
        "DUSt3R completely eliminates the need for camera calibration, feature extraction, epipolar geometry, and bundle adjustment. It re-frames 3D reconstruction as a direct regression task: a Vision Transformer takes two uncalibrated 2D images and directly predicts 3D coordinates for every single pixel in camera coordinate space.",
        "Testing core understanding of the neural revolution in 3D.",
        styles
    ))
    story.append(Spacer(1, 5))

    story.append(make_viva_box(
        "5", "What is a 'Digital Twin' in the context of forensic investigation?",
        "A forensic Digital Twin is a geometrically accurate, millimeter-scale, interactive 3D virtual counterpart of a physical crime scene. It freezes the exact physical state of the scene at the moment of documentation, ensuring permanent, repeatable, and non-destructive scientific analysis.",
        "Testing technical vocabulary and conceptual rigor.",
        styles
    ))
    story.append(Spacer(1, 5))

    story.append(make_viva_box(
        "6", "How does your system handle uncalibrated smartphone photos without EXIF metadata?",
        "Classical pipelines crash without EXIF metadata because they cannot compute focal length or sensor size. DUSt3R was pre-trained on massive multi-view datasets using Cross-View Completion (CroCo), allowing it to infer focal length and perspective depth implicitly from the visual context of the scene tokens.",
        "Checking understanding of camera calibration independence.",
        styles
    ))
    story.append(Spacer(1, 8))

    # Category B
    story.append(Paragraph("Category B: DUSt3R Neural Architecture & Global Optimization", styles['SectionH2']))
    story.append(make_viva_box(
        "7", "What are the two primary outputs generated by DUSt3R for each image pair?",
        "DUSt3R outputs: (1) A 3D Pointmap X of shape (H, W, 3), representing the 3D coordinates of each pixel expressed in Camera 1's reference frame; and (2) A Confidence Map C of shape (H, W), representing the network's geometric certainty for each predicted point.",
        "Checking basic knowledge of model tensor signatures.",
        styles
    ))
    story.append(Spacer(1, 5))

    story.append(make_viva_box(
        "8", "Why does DUSt3R use a Siamese Vision Transformer encoder rather than CNNs?",
        "A Siamese ViT breaks images into 16x16 patch tokens and models global relationships across the entire image using self-attention. Unlike CNNs, which have small local receptive fields and get confused by plain walls, Vision Transformers understand global room layout and continuity.",
        "Testing deep learning architecture knowledge.",
        styles
    ))
    story.append(Spacer(1, 5))

    story.append(make_viva_box(
        "9", "What role does Cross-Attention play in the DUSt3R decoder?",
        "Cross-attention allows tokens from Image 1 to query tokens from Image 2 as keys and values. It allows the network to dynamically search where a physical point in Image 1 appears in Image 2, directly computing stereoscopic disparity without explicit mathematical matching.",
        "Testing transformer mechanics understanding.",
        styles
    ))
    story.append(Spacer(1, 5))

    story.append(make_viva_box(
        "10", "How does the pipeline prevent memory exhaustion when processing 20 or more photos?",
        "Instead of constructing a complete all-pairs graph which scales quadratically (O(N^2)), the pipeline dynamically switches to a sliding window graph ('swin-3') for N > 5. Each image is paired only with its 3 adjacent neighbors. Furthermore, the neural network is purged from memory via 'del model' and 'empty_cache()' immediately after inference.",
        "Testing production engineering and memory optimization knowledge.",
        styles
    ))
    story.append(Spacer(1, 5))

    story.append(make_viva_box(
        "11", "Why do we need a Global Alignment step if DUSt3R already outputs 3D points?",
        "DUSt3R outputs pointmaps in the local coordinate frame of Camera 1 for each specific pair. Pair (1,2) and Pair (2,3) inhabit different coordinate systems. Global PointCloudOptimizer solves for the rigid 3D transformations (Rotation, Translation, Scale) across all cameras simultaneously to fuse them into a single unified room.",
        "Testing grasp of local vs global coordinate frames.",
        styles
    ))
    story.append(Spacer(1, 5))

    story.append(make_viva_box(
        "12", "Why is a Minimum Spanning Tree (MST) used before running gradient descent alignment?",
        "Gradient descent on camera poses is highly non-convex; starting with random camera poses causes optimization to get stuck in severe local minima. An MST connects cameras through the highest-confidence pairs first, providing an accurate initial pose guess that guarantees smooth convergence.",
        "Testing mathematical optimization intuition.",
        styles
    ))
    story.append(Spacer(1, 5))

    story.append(make_viva_box(
        "13", "What is the purpose of the confidence threshold (min_conf_thr = 1.5)?",
        "It acts as a filter that strips away points associated with ambiguous regions like transparent glass, shiny surfaces, sky, or motion blur. Rejecting points below 1.5 ensures only structurally verified points enter the point cloud.",
        "Checking data cleaning and quality control understanding.",
        styles
    ))
    story.append(Spacer(1, 8))

    # Category C
    story.append(Paragraph("Category C: Point Clouds, Surface Normals & Poisson Meshing", styles['SectionH2']))
    story.append(make_viva_box(
        "14", "Why does the pipeline save a deep copy of the dense point cloud before voxel downsampling?",
        "Voxel downsampling is necessary to clean geometric noise and speed up meshing, but it irreversibly destroys fine color detail. By saving a pristine copy of the dense point cloud, we can later use a KD-Tree to transfer photorealistic colors onto the final polygon mesh vertices.",
        "Testing memory of specific architectural decisions in code.",
        styles
    ))
    story.append(Spacer(1, 5))

    story.append(make_viva_box(
        "15", "How does Statistical Outlier Removal (SOR) decide which points to delete?",
        "For each point, it computes the mean distance to its 20 nearest neighbors. It then calculates the global mean and standard deviation of these distances. Any point whose local distance exceeds the global mean plus 2 standard deviations is flagged as an isolated noise point and purged.",
        "Testing mathematical understanding of point cloud filtering.",
        styles
    ))
    story.append(Spacer(1, 5))

    story.append(make_viva_box(
        "16", "How are surface normals calculated from raw, unorganized points?",
        "Using Principal Component Analysis (PCA). For each point, we find its 30 nearest spatial neighbors and compute their 3x3 covariance matrix. The eigenvector corresponding to the smallest eigenvalue defines the surface normal vector perpendicular to the local surface plane.",
        "Testing differential geometry foundations.",
        styles
    ))
    story.append(Spacer(1, 5))

    story.append(make_viva_box(
        "17", "What is the normal orientation problem and how is it resolved?",
        "PCA gives the axis of the normal, but cannot tell whether it points inward or outward. If neighbor normals point in opposite directions, surface reconstruction creates self-intersecting holes. We use a Riemannian Minimum Spanning Tree to propagate consistent normal directions across the entire cloud.",
        "Testing understanding of orientation consistency.",
        styles
    ))
    story.append(Spacer(1, 5))

    story.append(make_viva_box(
        "18", "What is the core intuition behind Screened Poisson Surface Reconstruction?",
        "Poisson reconstruction defines a continuous 3D Indicator Function that equals 1 inside physical objects and 0 outside in empty space. The surface of the crime scene is the boundary where this function transitions from 0 to 1, whose gradient field matches the point cloud surface normals.",
        "Testing ability to explain complex PDEs simply.",
        styles
    ))
    story.append(Spacer(1, 5))

    story.append(make_viva_box(
        "19", "Why did you choose Octree Depth 9 for the Poisson solver?",
        "An octree depth of 9 divides the room into 512 cells per side (2^9), delivering millimeter-scale spatial resolution (~2-5mm). This captures small forensic evidence (spent bullet casings, blood droplets) while operating safely within standard 16GB system RAM limits.",
        "Testing practical parameter selection justification.",
        styles
    ))
    story.append(Spacer(1, 5))

    story.append(make_viva_box(
        "20", "What is the Ball Pivoting Algorithm (BPA) and when is it used?",
        "BPA is a geometric meshing algorithm that simulates rolling a virtual sphere of specified radius over the point cloud. When the ball touches three points without falling through, a triangle is formed. We use BPA as a robust emergency fallback if the Poisson solver encounters an out-of-memory error.",
        "Testing understanding of fallback algorithms.",
        styles
    ))
    story.append(Spacer(1, 8))

    # Category D
    story.append(Paragraph("Category D: Post-Processing, Coordinate Rectification & Alignment", styles['SectionH2']))
    story.append(make_viva_box(
        "21", "Why do Poisson reconstructed meshes create 'melted wax' bubble artifacts over doors and windows?",
        "Poisson is a watertight solver: it mathematically insists on creating an enclosed solid volume. Where open doors, windows, or unphotographed regions exist, it interpolates artificial surfaces across empty space. We remove these by trimming vertices falling in the lowest 5th percentile of sampling density.",
        "Testing diagnostic understanding of reconstruction artifacts.",
        styles
    ))
    story.append(Spacer(1, 5))

    story.append(make_viva_box(
        "22", "How does KD-Tree color transfer work and why is it preferred over UV unwrapping?",
        "UV unwrapping on complex organic 3D scans creates severe seam tearing and distorted projections. Instead, we index the preserved dense point cloud in a 3D KD-Tree. For every mesh vertex, we perform an O(log N) nearest-neighbor query to instantly copy the exact photographic sRGB color from the original scan.",
        "Testing vertex coloring vs texture mapping tradeoffs.",
        styles
    ))
    story.append(Spacer(1, 5))

    story.append(make_viva_box(
        "23", "How does your code detect and fix an upside-down reconstructed crime scene?",
        "It inspects the rotation matrices of all reconstructed cameras. In OpenCV, camera-up is [0, -1, 0]. Transforming this vector into world space reveals each camera's upward direction. If the average Y-component is negative, the scene is inverted. We apply a 180° rotation around the X-axis to flip it upright.",
        "Testing coordinate frame mathematics.",
        styles
    ))
    story.append(Spacer(1, 5))

    story.append(make_viva_box(
        "24", "Why does align_and_export_room use median centering rather than mean centering?",
        "The arithmetic mean is highly sensitive to statistical outliers; a few stray floating points far away would pull the room's center away from the origin. The median operates independently along each axis and is robust against outliers, guaranteeing true geometric centering at (0,0,0).",
        "Testing statistical knowledge applied to 3D geometry.",
        styles
    ))
    story.append(Spacer(1, 5))

    story.append(make_viva_box(
        "25", "How does the pipeline establish real-world metric scale (1 unit = 1 meter)?",
        "Photos have scale ambiguity. In enhance_mesh.py, we calculate the vertical distance between the floor (Y=0) and the 95th percentile ceiling height. Standard residential architecture has a 3.2-meter ceiling. Scaling the mesh to match this standard ensures 1.0 unit in WebGL corresponds to 1.0 real-world meter.",
        "Testing practical engineering solutions to photogrammetry scale ambiguity.",
        styles
    ))
    story.append(Spacer(1, 5))

    story.append(make_viva_box(
        "26", "What is Euclidean Distance Transform (EDT) and how is it used in texture inpainting?",
        "EDT calculates the spatial distance from every blank, uncolored texel to the nearest valid colored texel. In enhance_mesh.py, it propagates the color of the nearest valid pixel into blank holes, seamlessly healing texture voids without blurring sharp boundaries.",
        "Testing image processing algorithms in mesh enhancement.",
        styles
    ))
    story.append(Spacer(1, 8))

    # Category E
    story.append(Paragraph("Category E: Navigation Grids & 3D Scene Object Detection", styles['SectionH2']))
    story.append(make_viva_box(
        "27", "How does detect_scene_objects.py identify room walls from raw 3D mesh points?",
        "It isolates vertices between 0.40m and 1.80m above the floor (human eye-level band) and computes 1D histograms along the X and Z axes. Dense physical drywall creates massive statistical peaks in these coordinate bins, allowing the algorithm to find East, West, North, and South wall planes automatically.",
        "Testing scene understanding and statistical geometric slicing.",
        styles
    ))
    story.append(Spacer(1, 5))

    story.append(make_viva_box(
        "28", "What height threshold distinguishes walkable floor from furniture obstacles in the NavGrid?",
        "Points within 8cm of the local fitted floor plane with upward normals are classified as walkable floor. Any surface rising between 12cm and 1.80m above local floor elevation is classified as a physical furniture obstacle (tables, chairs, beds).",
        "Testing exact parameter knowledge in navigation grid generation.",
        styles
    ))
    story.append(Spacer(1, 5))

    story.append(make_viva_box(
        "29", "Why is morphological binary dilation applied to the obstacle grid?",
        "Avatars in our simulation have non-zero physical body widths. If obstacles were single-pixel boundaries, pathfinding would allow characters to brush right against wall edges or clip their shoulders through furniture. Dilating obstacles by 1 cell (0.12m) ensures human body collision clearance.",
        "Testing practical robotics and game-pathfinding principles.",
        styles
    ))
    story.append(Spacer(1, 5))

    story.append(make_viva_box(
        "30", "What is the purpose of flip_glb.py and what downstream cascade does it trigger?",
        "flip_glb.py is an emergency 1-click remediation tool for operators. It applies a 180° X-axis rotation to the GLB model, resaves it, syncs it to frontend directories, and automatically re-executes calibrate_direction.py and detect_scene_objects.py so the compass and navigation grid update immediately.",
        "Testing maintenance, tooling, and pipeline integration.",
        styles
    ))
    story.append(Spacer(1, 8))

    # Category F
    story.append(Paragraph("Category F: Production Engineering, Concurrency & Systems", styles['SectionH2']))
    story.append(make_viva_box(
        "31", "Why did you enforce OMP_NUM_THREADS = 1 in reconstruct_dust3r.py?",
        "Open3D and PyTorch C++ extensions both initialize OpenMP thread pools. When run alongside Apple Silicon Metal GPU dispatch queues or Node.js worker threads, CPU thread contention causes race conditions, thread thrashing, and silent segmentation faults. Enforcing single-threading per process guarantees deterministic stability.",
        "Testing concurrency and low-level runtime knowledge.",
        styles
    ))
    story.append(Spacer(1, 5))

    story.append(make_viva_box(
        "32", "What does PYTORCH_ENABLE_MPS_FALLBACK = 1 achieve on Apple Silicon MacBooks?",
        "Apple's Metal Performance Shaders (MPS) framework does not implement every advanced tensor operation that CUDA supports. Setting this flag instructs PyTorch to smoothly execute any unsupported Metal operations on the CPU vector engine rather than throwing a fatal crash.",
        "Testing platform-specific acceleration architecture.",
        styles
    ))
    story.append(Spacer(1, 5))

    story.append(make_viva_box(
        "33", "Why did you use Server-Sent Events (SSE) instead of WebSockets for reconstruction progress?",
        "3D reconstruction progress is strictly a one-way diagnostic feed from server to client. WebSockets require complex bidirectional handshake management, ping-pong heartbeats, and custom reconnection logic. SSE runs over standard HTTP, natively supports automatic browser reconnection, and is lightweight and firewall-friendly.",
        "Testing web protocol design decisions.",
        styles
    ))
    story.append(Spacer(1, 5))

    story.append(make_viva_box(
        "34", "Why is the final output delivered as GLB format rather than OBJ or FBX?",
        "OBJ format requires multiple detached files (.obj, .mtl, image textures) which frequently break file paths during web deployment, and it does not support native vertex color packing. FBX is a proprietary Autodesk format. GLB is an open binary glTF standard that bundles geometry, vertex colors, and materials into a single compressed binary file that loads asynchronously in Three.js in milliseconds.",
        "Testing 3D web asset pipeline and format selection.",
        styles
    ))
    story.append(Spacer(1, 5))

    story.append(make_viva_box(
        "35", "What is the role of F=5.5 in room_bounds.json?",
        "F=5.5 is a hardcoded Stage Depth Marker. It defines the optimal focal distance along the Z-axis for the Three.js virtual camera controller, ensuring the forensic investigator spawns with a perfect full-room framing rather than inside a wall or in black empty space.",
        "Testing detailed knowledge of configuration files.",
        styles
    ))
    story.append(Spacer(1, 12))

    # ==================================================================
    # SUMMARY CONCLUSION CALLOUT
    # ==================================================================
    conclusion_text = (
        "<b>FINAL PROJECT DEFENSE SUMMARY:</b> Phase 2 bridges cutting-edge computer vision research and applied forensic "
        "engineering. By synthesizing direct neural pointmap regression (DUSt3R), robust global SE(3) optimization, "
        "resilient screened Poisson surface reconstruction, KD-Tree vertex color projection, automated 8-stage "
        "mesh enhancement, and dynamic 2D obstacle navigation grid rasterization, your project transforms arbitrary consumer "
        "smartphone photos into an admissible, millimeter-accurate 3D Forensic Digital Twin ready for real-time courtroom "
        "walkthroughs, ballistics simulations, and autonomous AI suspect pathfinding."
    )
    story.append(make_callout("EXAMINER SUMMARY STATEMENT", conclusion_text, LIGHT_BG_BLUE, BORDER_BLUE, NAVY_PRIMARY, styles))

    # Build the document
    print(f"Compiling publication-grade PDF to: {PDF_OUTPUT_PATH}")
    doc.build(story, canvasmaker=NumberedCanvas)
    print("PDF compilation successful!")

if __name__ == "__main__":
    build_pdf()
