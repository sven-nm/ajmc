import random
from pathlib import Path

import cv2
from typing import List, Tuple, Optional, Union
import numpy as np
from PIL import ImageFont, ImageDraw
from PIL import Image as PILImage

from ajmc.commons.docstrings import docstring_formatter, docstrings
from ajmc.commons.geometry import Shape
from ajmc.commons.miscellaneous import lazy_property, get_custom_logger, lazy_init
from ajmc.commons.variables import BoxType, COLORS, REGION_TYPES_TO_COLORS, TEXTCONTAINERS_TYPES_TO_COLORS

logger = get_custom_logger(__name__)


class Image:
    """Default class for ajmc images.

    Note:
          The center of `Image`-coordinates is the upper left corner, consistantly with cv2 and numpy. This implies
          that Y-coordinates are ascending towards the bottom of the image.
    """

    @lazy_init
    @docstring_formatter(**docstrings)
    def __init__(self,
                 id: Optional[str] = None,
                 path: Optional[str] = None,
                 matrix: Optional[np.ndarray] = None,
                 word_range: Optional[Tuple[int, int]] = None):
        """Default constructor.

        Args:
            id: The id of the image
            path: {path} to the image.
            matrix: an np.ndarray containing the image. Overrides self.matrix if not None.
            word_range: {word_range}
        """
        pass

    @lazy_property
    def matrix(self) -> np.ndarray:
        """np.ndarray of the image image matrix. Its shape is (height, width, channels)."""
        return cv2.imread(self.path)

    @lazy_property
    def height(self) -> int:
        return self.matrix.shape[0]

    @lazy_property
    def width(self) -> int:
        return self.matrix.shape[1]

    @lazy_property
    def contours(self):
        return find_contours(self.matrix)

    def crop(self,
             box: BoxType,
             margin: int = 0) -> 'Image':
        """Gets the slice of `self.matrix` corresponding to `box`.

        Args:
            box: The bbox delimiting the desired crop
            margin: The extra margin desired around `box`

        Returns:
             A new `Image` containing the desired crop.
        """
        cropped = self.matrix[box[0][1] - margin:box[1][1] + margin, box[0][0] - margin:box[1][0] + margin, :]

        return Image(matrix=cropped)

    def write(self, output_path: str):
        cv2.imwrite(output_path, self.matrix)

    def show(self):
        cv2.imshow('image', self.matrix)
        cv2.waitKey(0)
        cv2.destroyAllWindows()


def binarize(img_matrix: np.ndarray,
             inverted: bool = False):
    """Binarizes a cv2 `image`"""
    binarization_type = (cv2.THRESH_OTSU | cv2.THRESH_BINARY_INV) if inverted else (cv2.THRESH_OTSU | cv2.THRESH_BINARY)
    gray = cv2.cvtColor(img_matrix, cv2.COLOR_BGR2GRAY)
    return cv2.threshold(gray, 0, 255, type=binarization_type)[1]


def rgb_to_bgr(rgb: Tuple[int, int, int]) -> Tuple[int, int, int]:
    """Converts an RGB tuple to BGR."""
    return rgb[2], rgb[1], rgb[0]


def draw_box(box: BoxType,
             img_matrix: np.ndarray,
             stroke_color: Tuple[int, int, int] = (0, 0, 255),
             stroke_thickness: int = 1,
             fill_color: Optional[Tuple[int, int, int]] = None,
             fill_opacity: float = 1,
             text: str = None,
             text_size: float = .8,
             text_thickness: int = 2):
    """Draws a box on `img_matrix`.

    Args:
        box: A list of bboxes.
        img_matrix: The image matrix on which to draw the box.
        stroke_color: The color of the box contour.
        stroke_thickness: The thickness of the box contour.
        fill_color: The color of the box fill.
        fill_opacity: The opacity of the box fill.
        text: The text to be written on the box.
        text_size: The size of the text.
        text_thickness: The thickness of the text.

    Returns:
        np.ndarray: The modified `matrix`

    """

    if fill_color is not None:
        sub_img_matrix = img_matrix[box[0][1]:box[1][1], box[0][0]:box[1][0]]  # Creates the sub-image
        box_fill = sub_img_matrix.copy()  # Creates the fill to be added
        box_fill[:] = rgb_to_bgr(fill_color)  # Fills the fill with the desired color
        img_matrix[box[0][1]:box[1][1], box[0][0]:box[1][0]] = cv2.addWeighted(src1=sub_img_matrix,
                                                                               # Adds the fill to the image
                                                                               alpha=1 - fill_opacity,
                                                                               src2=box_fill,
                                                                               beta=fill_opacity,
                                                                               gamma=0)

    img_matrix = cv2.rectangle(img_matrix, pt1=box[0], pt2=box[1],
                               color=rgb_to_bgr(stroke_color),
                               thickness=stroke_thickness)

    if text is not None:
        # Start by getting the actual size of the text_box
        (text_width, text_height), _ = cv2.getTextSize(text, fontFace=cv2.FONT_HERSHEY_SIMPLEX,
                                                       fontScale=text_size,
                                                       thickness=text_thickness)

        # Draw a rectangle around the text
        img_matrix = cv2.rectangle(img_matrix,
                                   pt1=(box[1][0] - text_width - 4, box[0][1] - text_height - 4),
                                   pt2=(box[1][0], box[0][1]),
                                   color=rgb_to_bgr(stroke_color),
                                   thickness=-1)  # -1 means that the rectangle will be filled

        img_matrix = cv2.putText(img_matrix, text,
                                 org=(box[1][0] - text_width, box[0][1] - 2),
                                 fontFace=cv2.FONT_HERSHEY_SIMPLEX,
                                 fontScale=text_size,
                                 color=(255, 255, 255),
                                 thickness=text_thickness)

    return img_matrix


def draw_textcontainers(img_matrix, outfile: Optional[str] = None, *textcontainers):
    """Draws a list of `TextContainer`s on `img_matrix`."""

    # Get the set of textcontainer types
    for tc in textcontainers:
        if tc.type == 'region':
            img_matrix = draw_box(box=tc.bbox.bbox,
                                  img_matrix=img_matrix,
                                  stroke_color=REGION_TYPES_TO_COLORS[tc.region_type],
                                  stroke_thickness=2,
                                  fill_color=REGION_TYPES_TO_COLORS[tc.region_type],
                                  fill_opacity=.3,
                                  text=tc.region_type)

        elif tc.type in ['entity', 'sentence', 'hyphenation']:
            for i, bbox in enumerate(tc.bboxes):
                if i == len(
                        tc.bboxes) - 1:  # We write the region label text only if it's the last bbox to avoid overlap
                    img_matrix = draw_box(box=bbox.bbox,
                                          img_matrix=img_matrix,
                                          stroke_color=TEXTCONTAINERS_TYPES_TO_COLORS[tc.type],
                                          stroke_thickness=2,
                                          fill_color=TEXTCONTAINERS_TYPES_TO_COLORS[tc.type],
                                          fill_opacity=.3,
                                          text=tc.label if tc.type == 'entity' else tc.type)
                else:
                    img_matrix = draw_box(box=bbox.bbox,
                                          img_matrix=img_matrix,
                                          stroke_color=TEXTCONTAINERS_TYPES_TO_COLORS[tc.type],
                                          stroke_thickness=2,
                                          fill_color=TEXTCONTAINERS_TYPES_TO_COLORS[tc.type],
                                          fill_opacity=.3)


        else:
            img_matrix = draw_box(box=tc.bbox.bbox,
                                  img_matrix=img_matrix,
                                  stroke_color=TEXTCONTAINERS_TYPES_TO_COLORS[tc.type],
                                  stroke_thickness=1,
                                  fill_color=None,
                                  text=tc.type.capitalize())

    if outfile is not None:
        cv2.imwrite(outfile, img_matrix)

    return img_matrix


def draw_reading_order(matrix: np.ndarray,
                       page: Union['OcrPage', 'CanonicalPage'],
                       output_path: Optional[str] = None):
    # Compute word centers
    w_centers = [w.bbox.center for w in page.children.words]
    matrix = cv2.polylines(img=matrix,
                           pts=[np.array(w_centers, np.int32).reshape((-1, 1, 2))],
                           isClosed=False,
                           color=(255, 0, 0),
                           thickness=4)
    if output_path:
        cv2.imwrite(output_path, matrix)

    return matrix


def find_contours(img_matrix: np.ndarray,
                  binarize: bool = True) -> List[Shape]:
    """Binarizes `img_matrix` and finds contours using `cv2.findContours`."""

    # This has to be done in cv2. Using cv2.THRESH_BINARY_INV to avoid looking for the white background as a contour
    if binarize:
        gray = cv2.cvtColor(img_matrix, cv2.COLOR_BGR2GRAY)
        thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_OTSU | cv2.THRESH_BINARY_INV)[1]
    else:
        thresh = img_matrix

    # alternative: CHAIN_APPROX_NONE
    contours, _ = cv2.findContours(thresh, mode=cv2.RETR_EXTERNAL, method=cv2.CHAIN_APPROX_SIMPLE)

    # Discard single-point contours
    contours = [Shape.from_numpy_array(c) for c in contours if len(c) > 1]

    return contours


def draw_contours(image: Image, outfile: Optional[str] = None):
    white = np.zeros([image.matrix.shape[0], image.matrix.shape[1], 3], dtype=np.uint8)
    white.fill(255)

    for c in image.contours:
        color = (random.randint(0, 255),
                 random.randint(0, 255),
                 random.randint(0, 255))

        white = cv2.polylines(img=white,
                              pts=[np.array(c.points, np.int32).reshape((-1, 1, 2))],
                              isClosed=True,
                              color=color,
                              thickness=4)

        white = cv2.rectangle(white, pt1=c.bbox[0], pt2=c.bbox[1], color=color,
                              thickness=1)

    if outfile:
        cv2.imwrite(outfile, white)


def remove_artifacts_from_contours(contours: List[Shape],
                                   artifact_perimeter_threshold: float) -> List[Shape]:
    """Removes contours if the perimeter of their bounding box is inferior to `artifact_perimeter_threshold`"""

    contours_ = [c for c in contours if (2 * (c.width + c.height)) > artifact_perimeter_threshold]
    logger.info(f"""Removed {len(contours) - len(contours_)} artifacts""")

    return contours_


def resize_image(img: np.ndarray,
                 target_height) -> np.ndarray:
    """Resize image to target height while maintaining aspect ratio."""

    scale_percent = target_height / img.shape[0]  # percent of original size
    target_width = int(img.shape[1] * scale_percent)
    dim = target_width, target_height

    return cv2.resize(src=img, dsize=dim, interpolation=cv2.INTER_AREA)


def create_text_image(text: str,
                      font_path: Path,
                      padding: int,
                      image_height: int,
                      output_file: Optional[Path] = None) -> 'PIL.Image':
    """Draws text on a white image with given font, padding and image height."""
    # Todo come back here once tesseract experiments are done

    # Get the font size
    font_size = int(0.75*(image_height - 2 * padding))  # 0.75 for conversion from pixels to points

    # Get the font
    font = ImageFont.truetype(str(font_path), font_size)

    # Get the text size
    length = font.getlength(text)

    # Create the image
    image = PILImage.new('RGB', (int(length + 2 * padding), image_height), color='white')

    # Draw the text
    draw = ImageDraw.Draw(image)
    draw.text((padding, 0), text, font=font, fill='black')

    if output_file:
        image.save(output_file)

    return image

    # lines = {
    #     'modern_greek_line': 'Η Ελλάδα είναι μια χώρα στην Μεσόγειο, στην Ευρώπη',
    #     'polytonic_greek_line': 'μῆνιν ἄειδε θεὰ Πηληϊάδεω Ἀχιλῆος',
    #     'number_line': '1234567890',
    #     'english_line': 'The quick brown fox jumps',
    #     'mixed_line': '123. μῆνιν ἄειδε θεὰ — The quick brown fox jumps',
    # }
    #
    # output_dir = Path('/Users/sven/Desktop/test/')
    # for font in Path('data/greek_fonts').rglob('*.[ot]tf'):
    #     for type_, line in lines.items():
    #         create_text_image(text=line,
    #                           font_path=font,
    #                           padding=0,
    #                           image_height=100,
    #                           output_file=output_dir / f'{font.stem}_{type_}.png')


