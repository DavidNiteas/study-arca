"""Optional target-application preview and inspection for rendered decks."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .project import ProjectError


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inspect_native(pptx_path: Path | str) -> dict:
    try:
        from pptx import Presentation
    except ImportError as exc:
        raise ProjectError("缺少 python-pptx。安装：python -m pip install python-pptx") from exc
    path = Path(pptx_path).resolve()
    presentation = Presentation(path)
    slides = []
    for index, slide in enumerate(presentation.slides, 1):
        text_objects = sum(1 for shape in slide.shapes if getattr(shape, "has_text_frame", False) and shape.text)
        notes = slide.notes_slide.notes_text_frame.text if slide.has_notes_slide else ""
        slides.append({"slide": index, "shapes": len(slide.shapes), "text_objects": text_objects, "notes": bool(notes)})
    return {
        "slides": len(presentation.slides),
        "shapes": sum(item["shapes"] for item in slides),
        "text_objects": sum(item["text_objects"] for item in slides),
        "slides_with_notes": sum(item["notes"] for item in slides),
        "per_slide": slides,
    }


def _contact_sheet(images: list[Path], output: Path, *, columns: int, thumb_size=(386, 218)) -> Path:
    try:
        from PIL import Image, ImageDraw
    except ImportError as exc:
        raise ProjectError("缺少 Pillow。安装：python -m pip install pillow") from exc
    if not images:
        raise ProjectError("没有可用于联系表的预览图片")
    columns = max(1, columns)
    rows = (len(images) + columns - 1) // columns
    label_height = 22
    gap = 8
    cell_width = thumb_size[0] + gap * 2
    cell_height = thumb_size[1] + label_height + gap * 2
    canvas = Image.new("RGB", (columns * cell_width, rows * cell_height), "#E8ECE6")
    draw = ImageDraw.Draw(canvas)
    for index, image_path in enumerate(images):
        row, column = divmod(index, columns)
        x = column * cell_width + gap
        y = row * cell_height + gap
        with Image.open(image_path) as image:
            image = image.convert("RGB")
            image.thumbnail(thumb_size)
            canvas.paste(image, (x, y))
        draw.text((x, y + thumb_size[1] + 5), image_path.stem, fill="#193F36")
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, quality=92)
    return output


def make_contact_sheets(previews: list[Path], output_dir: Path | str, *, per_sheet: int = 6, columns: int = 2) -> list[Path]:
    output_dir = Path(output_dir)
    sheets = []
    for start in range(0, len(previews), per_sheet):
        batch = previews[start:start + per_sheet]
        path = output_dir / f"contact-{len(sheets) + 1}.jpg"
        sheets.append(_contact_sheet(batch, path, columns=columns))
    overview = output_dir / "all-slides-overview.jpg"
    _contact_sheet(previews, overview, columns=4, thumb_size=(240, 135))
    sheets.append(overview)
    return sheets


def render_powerpoint(
    pptx_path: Path | str,
    output_dir: Path | str,
    *,
    width: int = 2400,
    height: int = 1350,
    contact_per_sheet: int = 6,
    contact_columns: int = 2,
) -> dict:
    if not pptx_path:
        raise ProjectError("PPTX 路径不能为空")
    try:
        import win32com.client
    except ImportError as exc:
        raise ProjectError("缺少 pywin32；PowerPoint 预览需要 python -m pip install pywin32") from exc
    path = Path(pptx_path).resolve()
    if not path.is_file():
        raise ProjectError(f"PPTX 不存在：{path}")
    output_dir = Path(output_dir).resolve()
    previews_dir = output_dir / "previews"
    previews_dir.mkdir(parents=True, exist_ok=True)
    presentation = None
    application = None
    objects = []
    try:
        application = win32com.client.DispatchEx("PowerPoint.Application")
        presentation = application.Presentations.Open(str(path), ReadOnly=True, Untitled=False, WithWindow=False)
        for index in range(1, presentation.Slides.Count + 1):
            slide = presentation.Slides(index)
            slide.Export(str(previews_dir / f"{index:02d}.png"), "PNG", width, height)

            def visit(shapes):
                for item_index in range(1, shapes.Count + 1):
                    shape = shapes.Item(item_index)
                    value = {
                        "slide": index,
                        "id": shape.Name,
                        "type": int(shape.Type),
                        "frame_pt": [shape.Left, shape.Top, shape.Width, shape.Height],
                    }
                    if shape.Type == 6:
                        visit(shape.GroupItems)
                    elif shape.HasTextFrame and shape.TextFrame.HasText:
                        text_range = shape.TextFrame2.TextRange
                        value.update(
                            text=text_range.Text,
                            text_bounds_pt=[
                                text_range.BoundLeft,
                                text_range.BoundTop,
                                text_range.BoundWidth,
                                text_range.BoundHeight,
                            ],
                            overflow=(
                                text_range.BoundWidth > shape.Width + 1
                                or text_range.BoundHeight > shape.Height + 1
                            ),
                        )
                    objects.append(value)

            visit(slide.Shapes)
        presentation.SaveAs(str((output_dir / "deck.pdf").resolve()), 32)
        renderer = f"Microsoft PowerPoint {application.Version}"
    finally:
        if presentation is not None:
            presentation.Close()
        if application is not None:
            application.Quit()

    previews = sorted(previews_dir.glob("*.png"))
    contacts = make_contact_sheets(
        previews,
        output_dir,
        per_sheet=contact_per_sheet,
        columns=contact_columns,
    )
    overflow = [
        {"slide": item["slide"], "id": item["id"], "text": item.get("text", "")[:120]}
        for item in objects
        if item.get("overflow")
    ]
    result = {
        "renderer": renderer,
        "pptx": path.name,
        "pptx_sha256": sha256(path),
        "slides": len(previews),
        "objects": objects,
        "overflow": overflow,
        "native": inspect_native(path),
        "files": {
            str(item.relative_to(output_dir)): sha256(item)
            for item in previews + contacts + [output_dir / "deck.pdf"]
            if item.is_file()
        },
    }
    (output_dir / "measurements.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return result


def validate_preview(output_dir: Path | str, *, expected_slides: int | None = None) -> list[str]:
    output_dir = Path(output_dir).resolve()
    errors: list[str] = []
    measurements = output_dir / "measurements.json"
    if not measurements.is_file():
        return ["measurements.json 不存在"]
    try:
        data = json.loads(measurements.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [f"measurements.json 无法读取：{exc}"]
    slides = data.get("slides")
    if not isinstance(slides, int) or slides <= 0:
        errors.append("measurements.slides 非法")
    if expected_slides is not None and slides != expected_slides:
        errors.append(f"预览页数 {slides} 与期望 {expected_slides} 不一致")
    previews = sorted((output_dir / "previews").glob("*.png"))
    if len(previews) != slides:
        errors.append(f"预览图片 {len(previews)} 张与 measurements.slides 不一致")
    if not (output_dir / "all-slides-overview.jpg").is_file():
        errors.append("缺少 all-slides-overview.jpg")
    if not (output_dir / "deck.pdf").is_file():
        errors.append("缺少 deck.pdf")
    return errors
