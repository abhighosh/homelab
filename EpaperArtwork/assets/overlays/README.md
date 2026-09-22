# Foreground overlay sources

These transparent raster assets were generated with OpenAI's built-in image
generation tool, then alpha-cropped and reduced to a maximum dimension of 800
pixels. The renderer scales them down again before compositing and four-tone
quantisation on the NAS.

Visitor prompt template:

> Isolated complete [fox/rabbit/hedgehog/pheasant/cat/garden gnome] in a
> handmade monochrome pen-and-ink engraving style, transparent background,
> clear silhouette and restrained cross-hatching, designed to remain readable
> at roughly 45–70 pixels tall on a four-level greyscale e-paper display. One
> figure only; no scenery, plants, flowers, frame, lettering or colour.

Weather-detail prompts used the same handmade monochrome ink language and
transparent-background requirement for, respectively: a sparse scatter of
windblown autumn leaves; a few shallow driveway puddles with rain-ripple rings;
a short diagonal trail of muddy paw prints; and a short diagonal trail of paw
prints impressed in snow. Each requested one wide, low foreground element with
no scenery, plants, flowers, frame, lettering or colour.

The individual files remain separate so selection, placement and frequency are
deterministic renderer decisions rather than baked into the house artwork.
