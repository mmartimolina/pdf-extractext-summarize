"""Construcción del prompt enviado al proveedor de IA.

El prompt vive separado de la lógica de negocio para poder probarlo de
forma aislada y ajustarlo sin tocar la coordinación del flujo.
"""


def build_summary_prompt(text: str) -> str:
    """Construye el prompt de sumarización.

    El resumen conserva, por defecto, el idioma principal del texto de
    entrada y se limita a un máximo de 20 líneas.
    """
    return (
        "Resumí el siguiente texto de forma clara y concisa, conservando "
        "el idioma principal del texto original. No dejes frases "
        "incompletas. Máximo 20 líneas:\n\n"
        f"{text}"
    )
