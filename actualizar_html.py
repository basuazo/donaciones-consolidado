#!/usr/bin/env python3
"""Compatibilidad con el nombre antiguo del script.

La lógica de actualización vive en `actualizar.py` (una sola implementación,
escribiendo siempre en `index.html`). Este archivo se conserva para que
`python actualizar_html.py` siga funcionando.
"""

from actualizar import main

if __name__ == "__main__":
    main()
