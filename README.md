# Bioleach-gl-core · Gráfico Divulgativo Conceptual (PyOpenGL)

Este proyecto es una **representación gráfica, didáctica y divulgativa** en **Python** y **PyOpenGL** del proceso hidrometalúrgico de **biolixiviación de calcopirita** ($\text{CuFeS}_2$).

Creado con un enfoque visual ligero, código limpio y alta compatibilidad, este script busca comunicar de manera intuitiva los fundamentos microbianos y químicos de la extracción de cobre.

---

## ¿Qué representa este modelo conceptual?

La biolixiviación utiliza microorganismos para oxidar minerales sulfurados y extraer metales de valor de forma sostenible. Este script ilustra visualmente el siguiente ciclo redox simplificado:

$$\text{CuFeS}_2 + 4\text{Fe}^{3+} \longrightarrow \text{Cu}^{2+} + 5\text{Fe}^{2+} + 2\text{S}^0$$

Y el rol fundamental de la actividad microbiana en el sistema (regeneración del agente oxidante):

$$4\text{Fe}^{2+} + \text{O}_2 + 4\text{H}^+ \xrightarrow{\text{Bacterias}} 4\text{Fe}^{3+} + 2\text{H}_2\text{O}$$

* **Hierro Férrico ($\text{Fe}^{3+}$ - Violeta):** Agente oxidante que ataca la superficie de la partícula mineral.
* **Hierro Ferroso ($\text{Fe}^{2+}$ - Rosa):** Producto reducido que se aleja del mineral hacia la solución en descenso.
* **Bacterias (Verde):** Microorganismos oxidantes encargados de regenerar el $\text{Fe}^{2+}$ a $\text{Fe}^{3+}$ para sostener el ciclo.
* **Cobre Solubilizado ($\text{Cu}^{2+}$ - Naranja):** Iones liberados que migran hacia la bandeja de recolección inferior.
* **Mineral y Residuo:** Malla tridimensional procedural que muestra la transición visual del lecho sulfurado hacia un residuo empobrecido.

---

## Tecnologías y Librerías

* **Python 3**
* **PyOpenGL / PyQtGraph (OpenGL):** Renderizado gráfico en 3D optimizado mediante vértices y arrays con NumPy.
* **PyQt6:** Gestión de la ventana y superposición de la leyenda analítica en tiempo real (HTML/CSS).
* **NumPy:** Procesamiento matemático eficiente de matrices de partículas y vectores.

---

## Instalación y Ejecución

Sigue estos pasos para clonar y ejecutar la visualización en tu equipo:

1. **Clona el repositorio:**

   ```bash
   git clone [https://github.com/biosys-corner/bioleaching-opengl.git](https://github.com/biosys-corner/bioleaching-opengl.git)
   cd bioleaching-opengl
2. **Crea y activa un entorno virtual (opcional pero recomendado):**

    ```Bash
    python -m venv venv
    source venv/bin/activate  # En Linux/macOS
    # venv\Scripts\activate   # En Windows
    ```

3. **Instala las dependencias:**

    ```Bash
    pip install numpy pyqtgraph PyOpenGL PyQt6
    ```

4. **Ejecuta el script principal:**

    ```Bash
    python biolixiviacion_3d.py
    ```

# Roadmap / Próximas Versiones (v0.2+)

El proyecto evoluciona de manera orgánica. Las próximas características planeadas incluyen:

* [ ] **Optimización Gráfica Extrema:** Reducción de partículas a vértices puros sin texturas para garantizar un rendimiento fluido en hardware limitado.
* [ ] **Compatibilidad Estricta OpenGL 2.1:** Soporte asegurado para equipos antiguos y retro-computación.
* [ ] **Fallback por Software:** Renderizado alternativo en caso de ausencia de aceleración gráfica dedicada.
* [ ] **Paneles de Control Interactivos (Sliders):** Deslizadores en tiempo real para modificar tasas de irrigación y dinámicas del proceso.
* [ ] **Extensión del Proceso:** Incorporación visual de la etapa de separación y electro-obtención del cobre por medio de electrodos ($\text{EW}$).
