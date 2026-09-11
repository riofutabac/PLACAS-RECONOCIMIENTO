# Plan: Zona de análisis delimitada

**Source PRD**: `.claude/prds/placas-via-lastre.prd.md`
**Selected Milestone**: 1 — Zona de análisis delimitada
**Complexity**: Small

## Summary
Establecer la base del proyecto y dejar la zona de la vía de lastre definida como configuración versionada, no como números sueltos dentro de un script. El entregable es una máscara reproducible más una imagen de verificación superpuesta sobre un cuadro real, para que el analista confirme visualmente que la delimitación es correcta antes de invertir tiempo en detección y lectura de placas.

## Patterns to Mirror
No existe código previo en el repositorio. Los archivos `scan.py`, `seq.py` y `seq2.py` en la raíz son scripts desechables de la exploración inicial y no son referencia de estilo; se eliminan en la Tarea 1. Por lo tanto no hay patrones internos de nombres, errores, logging ni pruebas que imitar, y este plan los establece por primera vez siguiendo las reglas generales del proyecto: módulos pequeños y enfocados, validación en los límites, errores explícitos y sin valores mágicos incrustados.

| Category | Source | Pattern |
|---|---|---|
| Naming | — | Se establece aquí: módulos en `snake_case` bajo `lastre/`, constantes en `UPPER_SNAKE_CASE` |
| Errors | — | Se establece aquí: excepción propia por configuración inválida, fallo temprano y explícito |
| Tests | — | Se establece aquí: `pytest` en `tests/`, estructura Arrange-Act-Assert |

## Files to Change
| File | Action | Why |
|---|---|---|
| `scan.py`, `seq.py`, `seq2.py` | DELETE | Scripts de exploración ya cumplidos, no deben quedar como código muerto |
| `out/` | DELETE | Salidas de la exploración; el proyecto genera las suyas bajo una ruta configurada |
| `.gitignore` | CREATE | Excluir `.venv`, videos, salidas generadas y caché |
| `requirements.txt` | CREATE | Fijar `opencv-python`, `numpy`, `pytest` con versiones |
| `config/zona.json` | CREATE | Geometría de la zona y de la banda del reloj, editable sin tocar código |
| `lastre/__init__.py` | CREATE | Marcar el paquete |
| `lastre/config.py` | CREATE | Cargar y validar `config/zona.json`, fallar temprano si es inválido |
| `lastre/zona.py` | CREATE | Construir la máscara de la zona y responder si un punto o caja está dentro |
| `lastre/video.py` | CREATE | Abrir el video y entregar cuadros en secuencia, nunca por salto de índice |
| `scripts/verificar_zona.py` | CREATE | Generar la imagen de verificación con la zona superpuesta |
| `tests/test_zona.py` | CREATE | Probar la geometría de la máscara y la exclusión del reloj |
| `tests/test_config.py` | CREATE | Probar la validación de configuración inválida |

## Tasks

### Task 1: Limpiar la exploración y fijar el entorno
- **Action**: Eliminar `scan.py`, `seq.py`, `seq2.py` y `out/`. Crear `.gitignore` y `requirements.txt` con las versiones ya instaladas.
- **Mirror**: Sin referencia previa; se establece el patrón.
- **Validate**: `.venv/bin/pip install -r requirements.txt` y `ls` sin scripts sueltos en la raíz.

### Task 2: Configuración de la zona como dato
- **Action**: Crear `config/zona.json` con las dimensiones del cuadro, los dos puntos de la línea divisoria y la altura de la banda superior del reloj a excluir. Crear `lastre/config.py` que cargue el archivo, valide tipos y rangos, y lance una excepción propia con mensaje claro si algo falta o está fuera del cuadro.
- **Mirror**: Sin referencia previa; establece la validación en el límite del sistema.
- **Validate**: `.venv/bin/pytest tests/test_config.py`

### Task 3: Construcción de la máscara
- **Action**: Crear `lastre/zona.py` con una función que devuelva la máscara de la zona a partir de la configuración, y otra que responda si una caja delimitadora cae dentro. La banda del reloj queda excluida. Ninguna función muta su entrada.
- **Mirror**: Patrón inmutable de las reglas del proyecto: devolver nuevos arreglos, nunca modificar el recibido.
- **Validate**: `.venv/bin/pytest tests/test_zona.py`

### Task 4: Lectura secuencial de video
- **Action**: Crear `lastre/video.py` con un generador que entregue los cuadros en orden junto con su índice. Documentar que el salto por índice es inexacto en este códec y no debe usarse.
- **Mirror**: Sin referencia previa; establece el acceso a datos del proyecto.
- **Validate**: Recorrer una muestra y confirmar que el total de cuadros coincide con el reportado por OpenCV.

### Task 5: Evidencia visual de la delimitación
- **Action**: Crear `scripts/verificar_zona.py` que tome un video y un índice de cuadro, dibuje la zona en semitransparente y la banda excluida, y guarde la imagen resultante.
- **Mirror**: Sin referencia previa.
- **Validate**: Generar la imagen sobre la primera muestra y revisarla a simple vista.

## Validation
```bash
.venv/bin/pip install -r requirements.txt
.venv/bin/pytest -q
.venv/bin/python scripts/verificar_zona.py "Camara Placas 2_20260909105651-20260909163038(60).mp4" --frame 2697
```

## Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| La línea divisoria derivada de la anotación no coincide con el borde real | Media | La imagen de verificación se revisa antes de avanzar; los puntos se ajustan en el archivo de configuración sin tocar código |
| La banda del reloj se recorta de más y se pierde zona útil | Baja | La altura es configurable y la imagen de verificación la muestra dibujada |
| La zona queda correcta para un archivo pero no para otro | Baja | La cámara está confirmada como fija; aun así el script acepta cualquier video para volver a verificar |

## Acceptance
- [ ] Los scripts de exploración fueron eliminados y el entorno queda reproducible desde `requirements.txt`
- [ ] La geometría de la zona vive en `config/zona.json`, sin números incrustados en el código
- [ ] La banda superior del reloj queda excluida de la zona de análisis
- [ ] El acceso al video es secuencial y está documentado por qué
- [ ] La imagen de verificación existe y el analista confirma que la delimitación es correcta
- [ ] `.venv/bin/pytest -q` pasa

---
*Milestone 1 de 5. No se escribe código hasta recibir confirmación.*
