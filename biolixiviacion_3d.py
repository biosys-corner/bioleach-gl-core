"""Visualización didáctica de un ciclo conceptual de biolixiviación.

Requisitos: numpy, pyqtgraph con OpenGL y PyQt6.
Instalación habitual: pip install numpy pyqtgraph PyOpenGL PyQt6

Nota científica: es una animación conceptual, no un modelo cinético o
termodinámico. Las partículas y los tiempos se eligen para comunicar las fases.

Idea química representada (simplificada):
    CuFeS2 + 4 Fe³⁺  ->  Cu²⁺ + 5 Fe²⁺ + 2 S⁰
El Fe³⁺ (violeta) es el agente oxidante que ataca la calcopirita; al hacerlo
se reduce a Fe²⁺ (rosa), que se aleja del mineral hacia la solución.
"""

import sys
import numpy as np
import pyqtgraph.opengl as gl
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget


# ---------------------------------------------------------------------------
# Configuración de la demostración
# ---------------------------------------------------------------------------
ANCHO, ALTO = 1024, 600
FPS_MS = 20
# Tiempo simulado por frame. Con FPS_MS = 20 ms, 0.03 hace que el ciclo corra
# ~1.5 veces más rápido que el reloj real (a propósito: ciclo ágil).
PASO_TIEMPO = 0.03
# Tiempo mínimo antes de que un Fe²⁺ recién formado pueda regenerar Fe³⁺.
ESPERA_REGENERACION_FE2 = 0.5

DURACION_ACONDICIONAMIENTO = 3.0
DURACION_ACTIVA = 10.0
DURACION_AGOTADA = 7.0
DURACION_RECARGA = 3.0

DURACION_CICLO = (
    DURACION_ACONDICIONAMIENTO + DURACION_ACTIVA + DURACION_AGOTADA + DURACION_RECARGA
)


COLOR_MINERAL = (0.78, 0.48, 0.12, 1.0)
COLOR_AGOTADO = (0.38, 0.40, 0.42, 1.0)
COLOR_BACTERIAS = (0.10, 1.00, 0.28, 1.0)
COLOR_BACTERIAS_ADHERIDAS = (0.65, 1.00, 0.35, 1.0)
COLOR_COBRE = (1.00, 0.48, 0.16, 1.0)
COLOR_IRRIGACION = (0.08, 0.82, 1.00, 0.85)
COLOR_FE3 = (0.71, 0.48, 1.00, 1.0)  # Violeta: hierro férrico (oxidante)
COLOR_FE2 = (1.0, 0.25, 0.58, 1.0)  # Rosa: hierro ferroso (producto reducido)

# Geometría del mineral
RADIO_MINERAL = 2.25

# Hierro: parámetros de la animación
N_FE3 = 18
N_FE2 = 36  # Reserva de partículas Fe²⁺ reutilizables
N_FE3_REGENERADOS = 18  # Reserva independiente de Fe³⁺ regenerado
VEL_FE3 = 0.03  # Avance radial de Fe³⁺ por frame
PROB_CONVERSION = 0.55  # Probabilidad de que un Fe³⁺ que toca se vuelva Fe²⁺
MARGEN_CONTACTO = 0.02  # Tolerancia para considerar "contacto" con la superficie
FRAMES_VIDA_FE2 = 90  # Frames que dura visible cada Fe²⁺
DERIVA_FE2 = 0.006  # Deriva descendente de Fe²⁺ hacia la solución
RADIO_CONTACTO_BACTERIA = 0.65  # Distancia para detectar contacto Fe²⁺-bacteria

# Umbral para no reconstruir la malla del mineral por cambios imperceptibles
UMBRAL_COLOR = 0.01


rng = np.random.default_rng()


def _color_html(color):
    """Convierte una tupla RGBA (0-1) a '#rrggbb' para la leyenda."""
    r, g, b = (int(round(c * 255)) for c in color[:3])
    return f"#{r:02x}{g:02x}{b:02x}"


def _irregularidad_base(theta, phi):
    """Deformación suave y determinista de la roca (sin ruido por vértice)."""
    return (
        1.0
        + 0.09 * np.sin(3 * phi + 0.7) * np.sin(2 * theta)
        + 0.06 * np.cos(5 * phi - 1.3) * np.sin(3 * theta)
    )


def radio_superficie(direcciones):
    """
    Radio aproximado del mineral en cada dirección (vectores unitarios, Nx3).

    Usa la misma deformación que la malla, así las partículas "tocan" la roca
    real y no una esfera ideal. No incluye el ruido aleatorio por vértice
    (±0.1 unidades aprox.), que es cosmético.
    """
    x, y, z = direcciones[:, 0], direcciones[:, 1], direcciones[:, 2]
    theta = np.arccos(np.clip(z, -1.0, 1.0))
    phi = np.arctan2(y, x)
    return RADIO_MINERAL * _irregularidad_base(theta, phi)


def generar_geometria_mineral(filas=16, columnas=24, radio=RADIO_MINERAL):
    """
    Genera una roca irregular y dos paletas de color:
    mineral inicial y residuo visualmente empobrecido.
    """
    rng_local = np.random.default_rng(12)

    vertices = []

    for i in range(filas + 1):
        theta = np.pi * i / filas

        for j in range(columnas):
            phi = 2 * np.pi * j / columnas

            # Variación radial: rompe la simetría de la esfera.
            irregularidad = _irregularidad_base(theta, phi) + rng_local.uniform(
                -0.045, 0.045
            )

            r = radio * irregularidad

            x = r * np.sin(theta) * np.cos(phi)
            y = r * np.sin(theta) * np.sin(phi)
            z = r * np.cos(theta)

            vertices.append([x, y, z])

    vertices = np.asarray(vertices, dtype=float)
    caras = []

    # Cada cuadrilátero de la superficie se divide en dos triángulos.
    for i in range(filas):
        for j in range(columnas):
            actual = i * columnas + j
            siguiente = i * columnas + (j + 1) % columnas
            abajo = (i + 1) * columnas + j
            abajo_siguiente = (i + 1) * columnas + (j + 1) % columnas

            caras.append([actual, abajo, siguiente])
            caras.append([siguiente, abajo, abajo_siguiente])

    caras = np.asarray(caras, dtype=np.uint32)

    # Variaciones doradas y cobrizas entre las caras.
    tonos_mineral = np.array(
        [
            [0.78, 0.48, 0.12, 1.0],
            [0.88, 0.61, 0.20, 1.0],
            [0.68, 0.39, 0.09, 1.0],
            [0.82, 0.53, 0.16, 1.0],
        ]
    )

    tonos_agotado = np.array(
        [
            [0.38, 0.40, 0.42, 1.0],
            [0.46, 0.47, 0.48, 1.0],
            [0.32, 0.34, 0.36, 1.0],
            [0.42, 0.43, 0.44, 1.0],
        ]
    )

    indices_color = rng_local.integers(0, len(tonos_mineral), len(caras))

    colores_iniciales = tonos_mineral[indices_color]
    colores_agotados = tonos_agotado[indices_color]

    return vertices, caras, colores_iniciales, colores_agotados


class SimulacionBiolixiviacion(QWidget):
    """Ventana con escena OpenGL y una leyenda HTML superpuesta en 2D."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Biolixiviación cíclica | Modelo conceptual 3D")
        self.resize(ANCHO, ALTO)

        # La vista 3D y la leyenda son widgets hermanos. La leyenda NO se añade
        # con GLViewWidget.addItem(), que está reservado a objetos de la escena.
        self.vista = gl.GLViewWidget(self)
        self.vista.setGeometry(0, 0, ANCHO, ALTO)
        self.vista.setCameraPosition(distance=17, elevation=23, azimuth=35)
        self.vista.setBackgroundColor((13, 20, 29))

        self.leyenda = QLabel(self)
        self.leyenda.setTextFormat(Qt.TextFormat.RichText)
        self.leyenda.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self.leyenda.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.leyenda.setStyleSheet(
            "QLabel { background-color: rgba(10, 16, 24, 225); color: #edf2f7; "
            "border: 1px solid #526273; border-radius: 9px; padding: 12px; }"
        )
        self.leyenda.setGeometry(18, 18, 370, 360)

        self.leyenda.raise_()

        self.tiempo = 0.0
        self.angulo_camara = 35.0
        self.fase_actual = None  # "activa" | "pausa" | "recarga"
        self._color_aplicado = None  # Último progreso de color aplicado a la malla
        self._crear_escena()
        self._actualizar_leyenda("Preparando el ciclo…", "#ffd166", 0.0)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.actualizar)
        self.timer.start(FPS_MS)

    def resizeEvent(self, event):
        # Mantener ambas capas ajustadas al tamaño real de la ventana.
        self.vista.setGeometry(self.rect())
        self.leyenda.raise_()
        super().resizeEvent(event)

    def _crear_escena(self):
        # Rejilla horizontal y ejes de referencia.
        rejilla = gl.GLGridItem()
        rejilla.setSize(14, 14)
        rejilla.setSpacing(1, 1)
        rejilla.translate(0, 0, -3.0)
        self.vista.addItem(rejilla)

        ejes = gl.GLAxisItem()
        ejes.setSize(3, 3, 3)
        self.vista.addItem(ejes)

        # Mineral central: malla procedural irregular.
        (
            self.vertices_mineral,
            self.caras_mineral,
            self.colores_mineral,
            self.colores_agotado,
        ) = generar_geometria_mineral()

        malla = gl.MeshData(
            vertexes=self.vertices_mineral,
            faces=self.caras_mineral,
            faceColors=self.colores_mineral,
        )

        self.mineral = gl.GLMeshItem(
            meshdata=malla,
            smooth=False,
            drawEdges=False,
            drawFaces=True,
            drawFaceColors=True,
            shader="shaded",
            glOptions="opaque",
        )

        self.vista.addItem(self.mineral)

        # Un anillo discreto alrededor de la roca ayuda a sugerir la zona de riego.
        self.anillo = gl.GLLinePlotItem(
            pos=self._puntos_anillo(2.8, z=0.0),
            color=(0.2, 0.65, 0.9, 0.75),
            width=1.5,
            antialias=True,
            mode="line_strip",
        )
        self.vista.addItem(self.anillo)

        # Solución de irrigación: partículas cian que descienden sobre el mineral.
        self.n_gotas = 65
        self.pos_gotas = self._nuevas_gotas()

        colores_gotas = np.tile(np.array(COLOR_IRRIGACION), (self.n_gotas, 1))

        self.gotas = gl.GLScatterPlotItem(
            pos=self.pos_gotas,
            color=colores_gotas,
            size=5,
            pxMode=True,
            glOptions="translucent",
        )

        self.vista.addItem(self.gotas)

        # Bacterias: partículas verdes que se aproximan a la superficie.
        self.n_bacterias = 75
        self.pos_bacterias = self._nuevas_bacterias()
        # Movimiento lento e irregular de las bacterias libres.
        self.vel_bacterias = rng.normal(
            loc=0.0, scale=0.012, size=(self.n_bacterias, 3)
        )

        colores_b = np.tile(np.array(COLOR_BACTERIAS), (self.n_bacterias, 1))
        self.bacterias = gl.GLScatterPlotItem(
            pos=self.pos_bacterias,
            color=colores_b,
            size=7,
            pxMode=True,
            glOptions="opaque",
        )
        self.vista.addItem(self.bacterias)

        # Bacterias adheridas: población independiente sobre la superficie mineral.
        self.n_bacterias_adheridas = 32
        self.pos_bacterias_adheridas = self._nuevas_bacterias_adheridas()

        colores_b_adheridas = np.tile(
            np.array(COLOR_BACTERIAS_ADHERIDAS),
            (self.n_bacterias_adheridas, 1),
        )

        self.bacterias_adheridas = gl.GLScatterPlotItem(
            pos=self.pos_bacterias_adheridas,
            color=colores_b_adheridas,
            size=10,
            pxMode=True,
            glOptions="opaque",
        )
        self.bacterias_adheridas.setVisible(False)
        self.vista.addItem(self.bacterias_adheridas)

        # Cobre solubilizado: partículas naranjas liberadas cerca de la superficie.
        self.n_iones = 48
        self.pos_iones = self._nuevos_iones(inicial=True)
        colores_i = np.tile(np.array(COLOR_COBRE), (self.n_iones, 1))
        colores_i[:, 3] = 0.9

        self.iones = gl.GLScatterPlotItem(
            pos=self.pos_iones,
            color=colores_i,
            size=6,
            pxMode=True,
            glOptions="translucent",
        )
        self.vista.addItem(self.iones)

        # Hierro férrico (Fe³⁺): agente oxidante que se aproxima al mineral.
        self.n_fe3 = N_FE3
        self.pos_fe3 = self._nuevas_particulas_fe3()
        colores_fe3 = np.tile(np.array(COLOR_FE3), (self.n_fe3, 1))

        self.particulas_fe3 = gl.GLScatterPlotItem(
            pos=self.pos_fe3, color=colores_fe3, size=9, pxMode=True, glOptions="opaque"
        )
        self.vista.addItem(self.particulas_fe3)

        # Fe³⁺ regenerado por bacterias: reserva independiente.
        self.n_fe3_reg = N_FE3_REGENERADOS
        self.pos_fe3_reg = np.zeros((self.n_fe3_reg, 3), dtype=float)
        self.fe3_reg_activo = np.zeros(self.n_fe3_reg, dtype=bool)

        self.particulas_fe3_reg = gl.GLScatterPlotItem(
            pos=self.pos_fe3_reg,
            color=np.tile(np.array(COLOR_FE3), (self.n_fe3_reg, 1)),
            size=9,
            pxMode=True,
            glOptions="opaque",
        )
        self.particulas_fe3_reg.setVisible(False)
        self.vista.addItem(self.particulas_fe3_reg)

        # Hierro ferroso (Fe²⁺): producto reducido que se aleja del mineral.
        # Es una reserva de partículas reutilizables: cada una nace en el punto
        # donde un Fe³⁺ tocó la superficie y se desactiva al terminar su vida.
        self.n_fe2 = N_FE2
        self.pos_fe2 = np.zeros((self.n_fe2, 3), dtype=float)
        self.vel_fe2 = np.zeros((self.n_fe2, 3), dtype=float)
        self.fe2_vida = np.zeros(self.n_fe2, dtype=float)  # 0 (nace) -> 1 (muere)
        self.fe2_activo = np.zeros(self.n_fe2, dtype=bool)

        # Instante de activación de cada ranura Fe²⁺.
        self.ultimo_tiempo_fe2 = np.full(self.n_fe2, -np.inf, dtype=float)

        self.particulas_fe2 = gl.GLScatterPlotItem(
            pos=self.pos_fe2,
            color=np.tile(np.array(COLOR_FE2), (self.n_fe2, 1)),
            size=9,
            pxMode=True,
            glOptions="translucent",
        )
        self.particulas_fe2.setVisible(False)  # Se muestra con la 1ª conversión
        self.vista.addItem(self.particulas_fe2)

        # Bandeja conceptual inferior: destino visual de la solución cargada.
        self.bandeja = gl.GLLinePlotItem(
            pos=np.array(
                [
                    [-3.0, -2.5, -2.65],
                    [3.0, -2.5, -2.65],
                    [3.0, 2.5, -2.65],
                    [-3.0, 2.5, -2.65],
                    [-3.0, -2.5, -2.65],
                ]
            ),
            color=(0.1, 0.55, 0.95, 0.85),
            width=2,
            antialias=True,
        )
        self.vista.addItem(self.bandeja)

    def _actualizar_color_mineral(self, progreso):
        """Interpola los colores desde mineral inicial hasta residuo.

        Solo reconstruye la malla si el color cambió de forma perceptible.
        """
        progreso = float(np.clip(progreso, 0.0, 1.0))

        if (
            self._color_aplicado is not None
            and abs(progreso - self._color_aplicado) < UMBRAL_COLOR
        ):
            return
        self._color_aplicado = progreso

        colores = (
            1.0 - progreso
        ) * self.colores_mineral + progreso * self.colores_agotado

        malla = gl.MeshData(
            vertexes=self.vertices_mineral,
            faces=self.caras_mineral,
            faceColors=colores,
        )

        self.mineral.setMeshData(meshdata=malla)

    @staticmethod
    def _puntos_anillo(radio, z=0.0, n=100):
        angulos = np.linspace(0, 2 * np.pi, n)
        return np.column_stack(
            (radio * np.cos(angulos), radio * np.sin(angulos), np.full(n, z))
        )

    def _nuevas_bacterias(self):
        pos = np.empty((self.n_bacterias, 3), dtype=float)
        ang = rng.uniform(0, 2 * np.pi, self.n_bacterias)
        rad = rng.uniform(1.4, 3.2, self.n_bacterias)
        pos[:, 0] = rad * np.cos(ang)
        pos[:, 1] = rad * np.sin(ang)
        pos[:, 2] = rng.uniform(-2.0, 3.0, self.n_bacterias)
        return pos

    def _nuevas_bacterias_adheridas(self):
        """Distribuye bacterias sobre distintas caras de la roca irregular."""
        n = self.n_bacterias_adheridas

        # Direcciones uniformemente distribuidas alrededor de toda la roca.
        phi = rng.uniform(0, 2 * np.pi, n)
        z = rng.uniform(-1.0, 1.0, n)
        radio_xy = np.sqrt(1.0 - z**2)

        direcciones = np.column_stack(
            (
                radio_xy * np.cos(phi),
                radio_xy * np.sin(phi),
                z,
            )
        )

        # Separación mínima para evitar que las partículas queden enterradas
        # visualmente en la malla irregular.
        radios = radio_superficie(direcciones) + 0.08

        return direcciones * radios[:, None]

    def _nuevas_gotas(self):
        """Distribuye gotas en una zona superior a la roca."""
        pos = np.empty((self.n_gotas, 3), dtype=float)

        pos[:, 0] = rng.uniform(-1.7, 1.7, self.n_gotas)
        pos[:, 1] = rng.uniform(-1.7, 1.7, self.n_gotas)
        pos[:, 2] = rng.uniform(2.8, 5.5, self.n_gotas)

        return pos

    def _nuevos_iones(self, inicial=False):
        pos = np.empty((self.n_iones, 3), dtype=float)
        ang = rng.uniform(0, 2 * np.pi, self.n_iones)
        rad = rng.uniform(0.8, 2.0, self.n_iones)
        pos[:, 0] = rad * np.cos(ang)
        pos[:, 1] = rad * np.sin(ang)
        pos[:, 2] = (
            rng.uniform(-1.5, 1.2, self.n_iones)
            if inicial
            else rng.uniform(0.4, 1.8, self.n_iones)
        )
        return pos

    def _nuevas_particulas_fe3(self, n=None):
        """
        Genera n posiciones de Fe³⁺ alrededor del mineral (banda cercana al
        ecuador), a una distancia de 0.6-1.8 unidades por encima de la
        superficie real en esa dirección.
        """
        n = self.n_fe3 if n is None else n

        phi = rng.uniform(0, 2 * np.pi, n)
        cos_theta = rng.uniform(-0.7, 0.7, n)
        sin_theta = np.sqrt(1.0 - cos_theta**2)

        direcciones = np.column_stack(
            (sin_theta * np.cos(phi), sin_theta * np.sin(phi), cos_theta)
        )
        distancia = radio_superficie(direcciones) + rng.uniform(0.6, 1.8, n)

        return direcciones * distancia[:, None]

    # ------------------------------------------------------------------
    # Hierro: Fe³⁺ -> contacto -> Fe²⁺
    # ------------------------------------------------------------------
    def _activar_fe2(self, posiciones_impacto):
        """Activa Fe²⁺ en los puntos de impacto, mientras haya partículas libres."""
        libres = np.flatnonzero(~self.fe2_activo)
        k = min(len(libres), len(posiciones_impacto))
        if k == 0:
            return np.array([], dtype=int)

        ranuras = libres[:k]
        pos = posiciones_impacto[:k]

        # Se alejan radialmente del mineral, con una leve deriva hacia abajo
        # (hacia la solución que escurre a la bandeja).
        normas = np.linalg.norm(pos, axis=1, keepdims=True)
        direcciones = pos / normas
        rapidez = rng.uniform(0.018, 0.034, (k, 1))
        vel = direcciones * rapidez + rng.normal(0.0, 0.003, (k, 3))
        vel[:, 2] -= DERIVA_FE2

        self.pos_fe2[ranuras] = pos
        self.vel_fe2[ranuras] = vel
        self.fe2_vida[ranuras] = 0.0
        self.fe2_activo[ranuras] = True
        self.ultimo_tiempo_fe2[ranuras] = self.tiempo
        return ranuras

    def _activar_fe3_regenerado(self, indices_fe2):
        """Convierte Fe²⁺ en Fe³⁺ regenerado sin saltos de posición."""
        libres = np.flatnonzero(~self.fe3_reg_activo)
        k = min(len(libres), len(indices_fe2))

        if k == 0:
            return np.array([], dtype=int)

        ranuras_fe3 = libres[:k]
        ranuras_fe2 = indices_fe2[:k]

        # El Fe³⁺ nace exactamente donde estaba el Fe²⁺.
        self.pos_fe3_reg[ranuras_fe3] = self.pos_fe2[ranuras_fe2]
        self.fe3_reg_activo[ranuras_fe3] = True
        self.fe2_activo[ranuras_fe2] = False

        return ranuras_fe3

    def _mover_hierro(self):
        """Avanza Fe³⁺ hacia el mineral, convierte algunos en Fe²⁺ y mueve el Fe²⁺."""
        # --- Fe³⁺: aproximación radial a la superficie real de la roca ---
        distancias = np.linalg.norm(self.pos_fe3, axis=1)
        direcciones = self.pos_fe3 / distancias[:, None]
        r_superficie = radio_superficie(direcciones)

        self.pos_fe3 -= VEL_FE3 * direcciones
        distancias -= VEL_FE3

        alcanzadas = np.flatnonzero(distancias <= r_superficie + MARGEN_CONTACTO)

        if alcanzadas.size:
            # Algunas partículas (no todas) se reducen a Fe²⁺ en el punto de contacto.
            azar = rng.random(alcanzadas.size)
            convierten = alcanzadas[azar < PROB_CONVERSION]
            if convierten.size:
                self._activar_fe2(self.pos_fe3[convierten].copy())

            # Todas las que tocaron reinician su recorrido desde lejos.
            self.pos_fe3[alcanzadas] = self._nuevas_particulas_fe3(alcanzadas.size)

        self.particulas_fe3.setData(pos=self.pos_fe3)

        # --- Fe²⁺: se alejan, envejecen y pueden regenerarse ---
        activos = self.fe2_activo.copy()

        if activos.any():
            self.pos_fe2[activos] += self.vel_fe2[activos]
            self.fe2_vida[activos] += 1.0 / FRAMES_VIDA_FE2

            # Las partículas que terminan su vida dejan de estar activas.
            expiradas = self.fe2_activo & (self.fe2_vida >= 1.0)
            self.fe2_activo[expiradas] = False

        # Detectar Fe²⁺ que ha llegado a la zona de una bacteria.
        indices_contacto = self._fe2_en_contacto_bacteriano()

        if indices_contacto.size:
            # Evitar la regeneración inmediata de Fe²⁺ recién formado.
            tiempo_desde_activacion = (
                self.tiempo - self.ultimo_tiempo_fe2[indices_contacto]
            )
            maduros = indices_contacto[
                tiempo_desde_activacion >= ESPERA_REGENERACION_FE2
            ]

            if maduros.size:
                # La reserva independiente evita reposicionar Fe³⁺ en movimiento.
                self._activar_fe3_regenerado(maduros)

        # --- Fe³⁺ regenerado: vuelve hacia la superficie del mineral ---
        activos_reg = self.fe3_reg_activo

        if activos_reg.any():
            posiciones = self.pos_fe3_reg[activos_reg]
            distancias = np.linalg.norm(posiciones, axis=1)
            direcciones = posiciones / np.maximum(distancias[:, None], 1e-9)

            radios = radio_superficie(direcciones)
            distancias_nuevas = distancias - VEL_FE3

            # Avanzar radialmente hacia la roca.
            self.pos_fe3_reg[activos_reg] -= VEL_FE3 * direcciones

            # Al llegar a la superficie, el Fe³⁺ puede reducirse a Fe²⁺.
            alcanzadas_locales = distancias_nuevas <= radios + MARGEN_CONTACTO
            indices_reg = np.flatnonzero(activos_reg)
            alcanzadas = indices_reg[alcanzadas_locales]

            if alcanzadas.size:
                # Solo una parte de las partículas intenta convertirse.
                azar = rng.random(alcanzadas.size)
                convierten = alcanzadas[azar < PROB_CONVERSION]

                # Registrar cuáles consiguieron activar una ranura de Fe²⁺.
                convertidas_exitosas = np.array([], dtype=int)

                if convierten.size:
                    ranuras_fe2 = self._activar_fe2(self.pos_fe3_reg[convierten].copy())

                    # _activar_fe2 utiliza las primeras posiciones recibidas.
                    convertidas_exitosas = convierten[: len(ranuras_fe2)]

                # Las conversiones exitosas terminan como Fe³⁺.
                if convertidas_exitosas.size:
                    self.fe3_reg_activo[convertidas_exitosas] = False

                # Las demás partículas vuelven al exterior y pueden reintentarlo.
                fallidas = np.setdiff1d(alcanzadas, convertidas_exitosas)

                if fallidas.size:
                    self.pos_fe3_reg[fallidas] = self._nuevas_particulas_fe3(
                        len(fallidas)
                    )

            n_reg = int(self.fe3_reg_activo.sum())
            self.particulas_fe3_reg.setData(
                pos=self.pos_fe3_reg[self.fe3_reg_activo],
                color=np.tile(np.array(COLOR_FE3), (n_reg, 1)),
            )

            self.particulas_fe3_reg.setVisible(self.fe3_reg_activo.any())

        self._dibujar_fe2()

    def _dibujar_fe2(self):
        """Dibuja solo los Fe²⁺ activos; oculta el objeto si no hay ninguno."""
        activos = self.fe2_activo
        n_activos = int(activos.sum())

        if n_activos == 0:
            self.particulas_fe2.setVisible(False)
            return

        colores = np.tile(np.array(COLOR_FE2), (n_activos, 1))
        # Se desvanecen durante el último 40 % de su vida.
        colores[:, 3] = np.clip((1.0 - self.fe2_vida[activos]) / 0.4, 0.0, 1.0)

        self.particulas_fe2.setVisible(True)
        self.particulas_fe2.setData(pos=self.pos_fe2[activos], color=colores)

    def _fe2_en_contacto_bacteriano(self):
        """Devuelve los índices de Fe²⁺ activos próximos a alguna bacteria."""
        indices_activos = np.flatnonzero(self.fe2_activo)

        if indices_activos.size == 0:
            return np.array([], dtype=int)

        # Comparar cada Fe²⁺ activo con todas las bacterias.
        diferencias = (
            self.pos_fe2[indices_activos, np.newaxis, :]
            - self.pos_bacterias[np.newaxis, :, :]
        )
        distancias = np.linalg.norm(diferencias, axis=2)

        # Un Fe²⁺ entra en la zona si está cerca de al menos una bacteria.
        contacto = np.any(
            distancias <= RADIO_CONTACTO_BACTERIA,
            axis=1,
        )

        return indices_activos[contacto]

    # ------------------------------------------------------------------
    # Leyenda
    # ------------------------------------------------------------------
    def _actualizar_leyenda(self, estado, color, progreso):
        barra = max(0.0, min(100.0, progreso * 100.0))
        hex_fe3 = _color_html(COLOR_FE3)
        hex_fe2 = _color_html(COLOR_FE2)
        self.leyenda.setText(
            '<div style="font-family: sans-serif; font-size: 12px;">'
            '<div style="font-size:17px; font-weight:700; color:#ffd166;">'
            "BIO LIXIVIACIÓN · MODELO 3D</div>"
            '<div style="color:#aebdca; margin:3px 0 9px 0;">Ciclo conceptual de extracción de cobre</div>'
            f'<div><span style="color:#24ff63;">●</span> Bacterias: actividad biológica</div>'
            f'<div><span style="color:#14d1ff;">↓</span> Irrigación activa: solución lixiviante</div>'
            f'<div><span style="color:{hex_fe3};">●</span> Fe³⁺: hierro férrico (oxidante)</div>'
            f'<div><span style="color:{hex_fe2};">●</span> Fe²⁺: hierro ferroso (reducido)</div>'
            f'<div><span style="color:#ff7a29;">●</span> Cobre solubilizado: Cu²⁺</div>'
            f'<div><span style="color:#c58a25;">●</span> Mineral sulfurado</div>'
            f'<div><span style="color:#a2a8ad;">●</span> Residuo empobrecido (representación)</div>'
            '<hr style="border:0; border-top:1px solid #526273; margin:9px 0;">'
            '<div style="font-size:11px; color:#aebdca;">ESTADO DEL PROCESO</div>'
            f'<div style="font-size:14px; font-weight:700; color:{color}; margin:3px 0 8px 0;">{estado}</div>'
            '<div style="height:7px; background:#263746; border-radius:3px;">'
            f'<div style="height:7px; width:{barra:.1f}%; background:{color}; border-radius:3px;"></div></div>'
            '<div style="font-size:10px; color:#aebdca; margin-top:7px;">'
            "Esquema cualitativo; partículas, tiempos y colores no son datos experimentales.</div>"
            "</div>"
        )

    # ------------------------------------------------------------------
    # Control de fases
    # ------------------------------------------------------------------
    @staticmethod
    def _fase_para(t):
        if t < DURACION_ACONDICIONAMIENTO:
            return "acondicionamiento"

        t -= DURACION_ACONDICIONAMIENTO

        if t < DURACION_ACTIVA:
            return "activa"

        t -= DURACION_ACTIVA

        if t < DURACION_AGOTADA:
            return "pausa"

        return "recarga"

    def _entrar_fase(self, fase):
        """Inicializa y muestra las partículas de la fase correspondiente."""
        primer_ciclo = self.fase_actual is None

        if fase == "acondicionamiento":
            # Etapa 0: solo lluvia de solución lixiviante.
            self.pos_gotas[:] = self._nuevas_gotas()
            self.gotas.setVisible(True)

            # Ocultar las partículas químicas durante la introducción.
            self.particulas_fe3.setVisible(False)
            self.fe2_activo[:] = False
            self.particulas_fe2.setVisible(False)

            self.fe3_reg_activo[:] = False
            self.particulas_fe3_reg.setVisible(False)

            self.bacterias.setVisible(False)
            self.bacterias_adheridas.setVisible(False)
            self.iones.setVisible(False)

        elif fase == "activa":
            # Etapa 1: comienza la lixiviación química.
            self._actualizar_color_mineral(0.0)

            self.pos_fe3[:] = self._nuevas_particulas_fe3()
            self.particulas_fe3.setVisible(True)

            self.fe2_activo[:] = False
            self.particulas_fe2.setVisible(False)

            self.fe3_reg_activo[:] = False
            self.particulas_fe3_reg.setVisible(False)

            # La lluvia cesa: la solución deja de entrar visualmente.
            self.gotas.setVisible(False)

            self.pos_bacterias[:] = self._nuevas_bacterias()
            self.vel_bacterias[:] = rng.normal(
                loc=0.0,
                scale=0.012,
                size=(self.n_bacterias, 3),
            )
            self.bacterias.setVisible(True)
            self.bacterias_adheridas.setVisible(True)

            if not primer_ciclo:
                self.pos_iones[:] = self._nuevos_iones()

            self.iones.setVisible(True)

        elif fase == "pausa":
            # Etapa 2: pausa del riego y lecho empobrecido.
            self.particulas_fe3.setVisible(False)

            self.fe3_reg_activo[:] = False
            self.particulas_fe3_reg.setVisible(False)

            self.fe2_activo[:] = False
            self.particulas_fe2.setVisible(False)

            self.gotas.setVisible(False)

            self._actualizar_color_mineral(1.0)

        else:  # recarga
            # Etapa 3: transición visual hacia el siguiente ciclo.
            self.particulas_fe3.setVisible(False)

            self.fe3_reg_activo[:] = False
            self.particulas_fe3_reg.setVisible(False)

            self.fe2_activo[:] = False
            self.particulas_fe2.setVisible(False)

            self.gotas.setVisible(False)
            self.bacterias.setVisible(False)
            self.bacterias_adheridas.setVisible(False)
            self.iones.setVisible(False)

    def _mover_bacterias_libres(self):
        """Movimiento suave e irregular de las bacterias suspendidas."""
        # Variaciones pequeñas para evitar trayectorias completamente rectas.
        self.vel_bacterias += rng.normal(
            loc=0.0, scale=0.0015, size=self.vel_bacterias.shape
        )

        # Limitar la velocidad para mantener un desplazamiento discreto.
        rapidez = np.linalg.norm(self.vel_bacterias, axis=1)
        max_rapidez = 0.025
        demasiado_rapidas = rapidez > max_rapidez

        if np.any(demasiado_rapidas):
            self.vel_bacterias[demasiado_rapidas] *= (
                max_rapidez / rapidez[demasiado_rapidas]
            )[:, None]

        # Aplicar el desplazamiento.
        self.pos_bacterias += self.vel_bacterias

        # Mantener las bacterias dentro de una región cilíndrica.
        radio_max = 3.5
        z_min = -2.0
        z_max = 3.0

        # Confinamiento lateral: si una bacteria rebasa el radio,
        # vuelve al borde y refleja su velocidad hacia el interior.
        radios_xy = np.linalg.norm(self.pos_bacterias[:, :2], axis=1)
        fuera_lateral = radios_xy > radio_max

        if np.any(fuera_lateral):
            # Dirección radial de cada bacteria que salió del límite.
            normales = (
                self.pos_bacterias[fuera_lateral, :2] / radios_xy[fuera_lateral, None]
            )

            # Situarla justo en el borde del cilindro.
            self.pos_bacterias[fuera_lateral, :2] = normales * radio_max

            # Reflejar solo la componente de velocidad que apunta hacia fuera.
            velocidades_xy = self.vel_bacterias[fuera_lateral, :2]
            componente_radial = np.sum(velocidades_xy * normales, axis=1)
            hacia_fuera = componente_radial > 0

            velocidades_xy[hacia_fuera] -= (
                2 * componente_radial[hacia_fuera, None] * normales[hacia_fuera]
            )
            self.vel_bacterias[fuera_lateral, :2] = velocidades_xy

        # Confinamiento vertical: reflejar el movimiento en ambos extremos.
        debajo = self.pos_bacterias[:, 2] < z_min
        encima = self.pos_bacterias[:, 2] > z_max

        self.pos_bacterias[debajo, 2] = z_min
        self.pos_bacterias[encima, 2] = z_max

        self.vel_bacterias[debajo, 2] = np.abs(self.vel_bacterias[debajo, 2])
        self.vel_bacterias[encima, 2] = -np.abs(self.vel_bacterias[encima, 2])

    def _paso_acondicionamiento(self, t):
        """Etapa 0: entrada visual de solución lixiviante."""
        self.pos_gotas[:, 2] -= 0.09

        gotas_agotadas = self.pos_gotas[:, 2] < 2.25

        if np.any(gotas_agotadas):
            nuevas_gotas = self._nuevas_gotas()
            self.pos_gotas[gotas_agotadas] = nuevas_gotas[gotas_agotadas]

        return "ETAPA 0 · ACONDICIONAMIENTO DEL LECHO", "#14d1ff"

    def _paso_activa(self, t):
        # Fase 1: riego y extracción conceptual.
        self._actualizar_color_mineral(t / DURACION_ACTIVA)

        # Hierro: Fe³⁺ se aproxima, algunos se convierten en Fe²⁺ que se aleja.
        self._mover_hierro()

        self._mover_bacterias_libres()

        # La solución desciende durante el riego activo.
        self.pos_gotas[:, 2] -= 0.09

        # Las partículas que alcanzan la superficie vuelven arriba.
        gotas_agotadas = self.pos_gotas[:, 2] < 2.25
        if np.any(gotas_agotadas):
            nuevas_gotas = self._nuevas_gotas()
            self.pos_gotas[gotas_agotadas] = nuevas_gotas[gotas_agotadas]

        # Iones aparecen cerca del mineral y migran hacia la bandeja de solución.
        nuevas = self.pos_iones[:, 2] < -2.3
        if np.any(nuevas):
            reemplazo = self._nuevos_iones()
            self.pos_iones[nuevas] = reemplazo[nuevas]
        self.pos_iones[:, 2] -= 0.035

        return "FASE 1 · RIEGO Y SOLUBILIZACIÓN", "#45ed83"

    def _paso_pausa(self, t):
        # Fase 2: el lecho está en pausa; el modelo no produce más iones.
        self._mover_bacterias_libres()
        self.pos_iones[:, 2] -= 0.045
        self.pos_iones[:, 2] = np.maximum(self.pos_iones[:, 2], -2.6)

        return "FASE 2 · LECHO EN PAUSA / MINERAL EMPOBRECIDO", "#ff8585"

    def _paso_recarga(self, t):
        # Fase 3: limpieza visual y transición al siguiente ciclo.
        t_recarga = t - DURACION_ACTIVA - DURACION_AGOTADA
        if t_recarga < DURACION_RECARGA / 2:
            self._actualizar_color_mineral(1.0)
        else:
            self._actualizar_color_mineral(0.0)

        return "FASE 3 · RETIRO DE RESIDUO Y RECARGA", "#77bfff"

    def actualizar(self):
        self.tiempo += PASO_TIEMPO
        t = self.tiempo % DURACION_CICLO

        fase = self._fase_para(t)
        if fase != self.fase_actual:
            self._entrar_fase(fase)
            self.fase_actual = fase

        if fase == "acondicionamiento":
            estado, color_estado = self._paso_acondicionamiento(t)

        elif fase == "activa":
            t_fase = t - DURACION_ACONDICIONAMIENTO
            estado, color_estado = self._paso_activa(t_fase)

        elif fase == "pausa":
            t_fase = t - DURACION_ACONDICIONAMIENTO - DURACION_ACTIVA
            estado, color_estado = self._paso_pausa(t_fase)

        else:
            t_fase = t - DURACION_ACONDICIONAMIENTO - DURACION_ACTIVA - DURACION_AGOTADA
            estado, color_estado = self._paso_recarga(t_fase)

        self.bacterias.setData(pos=self.pos_bacterias)
        self.iones.setData(pos=self.pos_iones)
        self.gotas.setData(pos=self.pos_gotas)
        self._actualizar_leyenda(estado, color_estado, t / DURACION_CICLO)


def main():
    app = QApplication(sys.argv)
    simulacion = SimulacionBiolixiviacion()
    simulacion.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
