# Enmienda 001 a la pre-registración EXP-005

**Fecha efectiva**: 2026-07-23 (Europe/Madrid)

La pre-registración original fue incorporada en el commit `3f01143`, cuyo
timestamp es 2026-07-23 00:34 +0200, pero el documento declaraba fecha
2026-07-21 y una ventana iniciada el 2026-07-22. Esa cronología no permite
calificar como prospectivos los partidos del 22-jul.

Para preservar una frontera auditable sin reescribir silenciosamente el
registro original:

- la ventana confirmatoria se inicia el **2026-07-27 00:00**, primer lunes
  completo posterior al commit de registro;
- todo partido del 2026-07-22 al 2026-07-26 queda fuera de la evaluación
  confirmatoria y, si se inspecciona, se etiqueta exploratorio;
- el cierre se mantiene en 2026-11-30 (exclusivo si se implementa como
  intervalo semiabierto `[2026-07-27, 2026-11-30)`);
- las hipótesis H1–H5, modelos, métricas, semilla y regla de una sola pasada
  permanecen sin cambios;
- cualquier implementación de `dc_dyn_gamma` debe quedar cerrada antes de
  usar partidos desde el 2026-07-27 y debe documentarse en una nueva enmienda
  con el hash exacto del commit.

Esta enmienda es parte integral del registro. El archivo original se conserva
para que el error de fecha y su corrección sean visibles.
