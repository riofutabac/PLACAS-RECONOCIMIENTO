"""Adaptador para detectores YOLO (YOLO26) sobre ONNX Runtime.

Permite ejecutar modelos YOLO26 exportados a ONNX con NMS integrado, realizando
el preprocesamiento (letterbox, RGB, normalización FP32) y posprocesamiento
(desescalado a coordenadas originales del cuadro) sin dependencias de PyTorch
ni Ultralytics en tiempo de inferencia.
"""

import ast
from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import cv2
import numpy as np

from lastre.aceleracion import configurar_opciones_sesion


class YOLODeteccionError(RuntimeError):
    """Excepción lanzada ante errores de carga o inferencia en el modelo YOLO."""


@dataclass(frozen=True)
class CajaEsquinas:
    """Coordenadas de esquinas de una detección en el espacio original de la imagen."""
    x1: int
    y1: int
    x2: int
    y2: int


@dataclass(frozen=True)
class DeteccionCruda:
    """Resultado individual de detección compatible con el contrato de open_image_models."""
    bounding_box: CajaEsquinas
    label: str
    confidence: float


# Catálogo estándar COCO de 80 clases
COCO_CLASSES: Dict[int, str] = {
    0: "person", 1: "bicycle", 2: "car", 3: "motorcycle", 4: "airplane",
    5: "bus", 6: "train", 7: "truck", 8: "boat", 9: "traffic light",
    10: "fire hydrant", 11: "stop sign", 12: "parking meter", 13: "bench",
    14: "bird", 15: "cat", 16: "dog", 17: "horse", 18: "sheep", 19: "cow",
    20: "elephant", 21: "bear", 22: "zebra", 23: "giraffe", 24: "backpack",
    25: "umbrella", 26: "handbag", 27: "tie", 28: "suitcase", 29: "frisbee",
    30: "skis", 31: "snowboard", 32: "sports ball", 33: "kite",
    34: "baseball bat", 35: "baseball glove", 36: "skateboard", 37: "surfboard",
    38: "tennis racket", 39: "bottle", 40: "wine glass", 41: "cup", 42: "fork",
    43: "knife", 44: "spoon", 45: "bowl", 46: "banana", 47: "apple",
    48: "sandwich", 49: "orange", 50: "broccoli", 51: "carrot", 52: "hot dog",
    53: "pizza", 54: "donut", 55: "cake", 56: "chair", 57: "couch",
    58: "potted plant", 59: "bed", 60: "dining table", 61: "toilet", 62: "tv",
    63: "laptop", 64: "mouse", 65: "remote", 66: "keyboard", 67: "cell phone",
    68: "microwave", 69: "oven", 70: "toaster", 71: "sink", 72: "refrigerator",
    73: "book", 74: "clock", 75: "vase", 76: "scissors", 77: "teddy bear",
    78: "hair drier", 79: "toothbrush"
}


def calcular_hash_archivo(ruta: Path) -> str:
    """Calcula el resumen criptográfico SHA256 de un archivo binario."""
    sha = hashlib.sha256()
    with ruta.open("rb") as f:
        while bloque := f.read(65536):
            sha.update(bloque)
    return sha.hexdigest()


def resolver_ruta_modelo_yolo(modelo: Union[str, Path]) -> Path:
    """Ubica el archivo .onnx del modelo solicitado en las rutas estándar."""
    p = Path(modelo)
    if p.is_file():
        return p.resolve()

    nombre = f"{modelo}.onnx" if not str(modelo).endswith(".onnx") else str(modelo)
    candidatos = [
        Path(nombre),
        Path("modelos") / nombre,
        Path(__file__).resolve().parent.parent / nombre,
        Path(__file__).resolve().parent.parent / "modelos" / nombre,
    ]
    for candidato in candidatos:
        if candidato.is_file():
            return candidato.resolve()

    # Si no existe en disco, intentar exportar automáticamente si ultralytics está disponible
    try:
        from ultralytics import YOLO
        stem = Path(nombre).stem
        m = YOLO(f"{stem}.pt")
        export_path = m.export(format="onnx", imgsz=640)
        if Path(export_path).is_file():
            return Path(export_path).resolve()
    except Exception:
        pass

    rutas_probadas = [str(c) for c in candidatos]
    raise YOLODeteccionError(
        f"No se encontró el archivo del modelo YOLO '{modelo}'. "
        f"Rutas examinadas: {rutas_probadas}"
    )


class YOLO26Detector:
    """Detector de objetos basado en YOLO26 exportado a ONNX Runtime FP32."""

    def __init__(
        self,
        modelo: Union[str, Path] = "yolo26n",
        proveedores: Optional[Sequence[str]] = None,
        hilos: Optional[int] = None,
        tamano_entrada: Tuple[int, int] = (640, 640),
        session: Optional[Any] = None,
    ) -> None:
        """Inicializa la sesión ONNX Runtime y extrae metadatos del modelo."""
        self._nombre_modelo = str(modelo)
        self._tamano_entrada = tamano_entrada
        self._classes = dict(COCO_CLASSES)

        if session is not None:
            self._session = session
            self._ruta_modelo = Path(str(modelo))
            self._peso_hash = "mock_session"
        else:
            self._ruta_modelo = resolver_ruta_modelo_yolo(modelo)
            self._peso_hash = calcular_hash_archivo(self._ruta_modelo)

            try:
                import onnxruntime as ort
            except ImportError as exc:  # pragma: no cover
                raise YOLODeteccionError(
                    "onnxruntime no está instalado; es necesario para ejecutar YOLO26"
                ) from exc

            sess_options = configurar_opciones_sesion(hilos)
            kwargs = {}
            if sess_options is not None:
                kwargs["sess_options"] = sess_options
            if proveedores:
                kwargs["providers"] = list(proveedores)
            else:
                kwargs["providers"] = ["CPUExecutionProvider"]

            try:
                self._session = ort.InferenceSession(str(self._ruta_modelo), **kwargs)
            except Exception as exc:
                raise YOLODeteccionError(
                    f"No fue posible inicializar la sesión ONNX para '{self._ruta_modelo}': {exc}"
                ) from exc

        # Exponer atributos para que `proveedores_activos` de `lastre.aceleracion` funcione
        self.model = self._session
        self.session = self._session

        # Inspeccionar nombres y dimensiones de entradas/salidas si es sesión ONNX real
        if hasattr(self._session, "get_inputs"):
            entradas = self._session.get_inputs()
            if not entradas:
                raise YOLODeteccionError(f"El modelo {self._ruta_modelo} no tiene entradas definidas.")
            self._nombre_entrada = entradas[0].name
        else:
            self._nombre_entrada = "images"

        # Leer diccionario de clases del modelo ONNX si está presente
        if hasattr(self._session, "get_modelmeta"):
            meta = self._session.get_modelmeta()
            meta_dict = getattr(meta, "custom_metadata_map", {}) or {}
            if "names" in meta_dict:
                try:
                    nombres_parseados = ast.literal_eval(meta_dict["names"])
                    if isinstance(nombres_parseados, dict):
                        self._classes = {int(k): str(v) for k, v in nombres_parseados.items()}
                except (ValueError, SyntaxError):
                    pass

    @property
    def peso_hash(self) -> str:
        """Hash criptográfico SHA256 del archivo ONNX."""
        return self._peso_hash

    @property
    def ruta_modelo(self) -> Path:
        """Ruta resuelta del archivo de pesos."""
        return self._ruta_modelo

    @property
    def nombre_modelo(self) -> str:
        """Nombre o identificador del modelo."""
        return self._nombre_modelo

    @property
    def tamano_entrada(self) -> Tuple[int, int]:
        """Dimensiones esperadas de entrada (alto, ancho)."""
        return self._tamano_entrada

    def preprocesar(self, cuadro: np.ndarray) -> Tuple[np.ndarray, float, int, int]:
        """Aplica letterbox a (640, 640), convierte a RGB y normaliza a tensor NCHW FP32."""
        if not isinstance(cuadro, np.ndarray):
            raise YOLODeteccionError(
                f"El cuadro debe ser un numpy.ndarray, se recibió: {type(cuadro).__name__}"
            )
        if cuadro.ndim != 3 or cuadro.shape[2] != 3:
            raise YOLODeteccionError(
                f"El cuadro debe tener forma (H, W, 3), se recibió: {cuadro.shape}"
            )
        if cuadro.size == 0:
            raise YOLODeteccionError("El cuadro no puede estar vacío (tamaño 0).")

        alto_orig, ancho_orig = cuadro.shape[:2]
        dest_h, dest_w = self._tamano_entrada

        escala = min(dest_h / alto_orig, dest_w / ancho_orig)
        nw = int(round(ancho_orig * escala))
        nh = int(round(alto_orig * escala))

        redimensionado = cv2.resize(cuadro, (nw, nh), interpolation=cv2.INTER_LINEAR)
        pad_w = (dest_w - nw) // 2
        pad_h = (dest_h - nh) // 2

        padded = np.full((dest_h, dest_w, 3), 114, dtype=np.uint8)
        padded[pad_h:pad_h + nh, pad_w:pad_w + nw] = redimensionado

        rgb = cv2.cvtColor(padded, cv2.COLOR_BGR2RGB)
        tensor = rgb.astype(np.float32) / 255.0
        tensor = np.transpose(tensor, (2, 0, 1))[np.newaxis, ...]
        return tensor, escala, pad_w, pad_h

    def predict(
        self, images: Union[np.ndarray, Sequence[np.ndarray]]
    ) -> Union[List[DeteccionCruda], List[List[DeteccionCruda]]]:
        """Ejecuta la inferencia sobre una imagen o secuencia de imágenes.

        Devuelve objetos con `.bounding_box`, `.label` y `.confidence`, con
        coordenadas transformadas al tamaño original de cada imagen.
        """
        es_individual = isinstance(images, np.ndarray)
        lista_imagenes = [images] if es_individual else list(images)

        resultados: List[List[DeteccionCruda]] = []
        for img in lista_imagenes:
            tensor, escala, pad_w, pad_h = self.preprocesar(img)
            alto_orig, ancho_orig = img.shape[:2]

            salidas = self._session.run(None, {self._nombre_entrada: tensor})
            if not salidas:
                resultados.append([])
                continue

            # La salida esperada es (1, 300, 6) con [x1, y1, x2, y2, conf, cls_id]
            predicciones = salidas[0]
            if predicciones.ndim == 3 and predicciones.shape[0] == 1:
                predicciones = predicciones[0]
            if predicciones.ndim != 2 or predicciones.shape[1] != 6:
                raise YOLODeteccionError(
                    f"Salida ONNX incompatible: {predicciones.shape}; se requiere (1, N, 6) o (N, 6)."
                )

            detecciones: List[DeteccionCruda] = []
            for fila in predicciones:
                if not np.isfinite(fila).all():
                    continue
                if not 0 <= fila[4] <= 1 or fila[5] != int(fila[5]):
                    continue
                conf = float(fila[4])
                cls_id = int(fila[5])

                # Revertir traslación y escala del letterbox
                x1_orig = (float(fila[0]) - pad_w) / escala
                y1_orig = (float(fila[1]) - pad_h) / escala
                x2_orig = (float(fila[2]) - pad_w) / escala
                y2_orig = (float(fila[3]) - pad_h) / escala

                # Acotar a los límites del cuadro original
                x1 = max(0, min(ancho_orig, int(round(x1_orig))))
                y1 = max(0, min(alto_orig, int(round(y1_orig))))
                x2 = max(0, min(ancho_orig, int(round(x2_orig))))
                y2 = max(0, min(alto_orig, int(round(y2_orig))))

                if x2 > x1 and y2 > y1:
                    etiqueta = self._classes.get(cls_id, str(cls_id))
                    detecciones.append(
                        DeteccionCruda(
                            bounding_box=CajaEsquinas(x1=x1, y1=y1, x2=x2, y2=y2),
                            label=etiqueta,
                            confidence=conf,
                        )
                    )
            resultados.append(detecciones)

        return resultados[0] if es_individual else resultados
