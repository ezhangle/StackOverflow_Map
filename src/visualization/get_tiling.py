#!/usr/bin/env python3

import os
import os.path
import shutil

import sys
import csv

import heapq
from collections import namedtuple

from concurrent.futures import ThreadPoolExecutor

from PIL import Image, ImageDraw, ImageOps, ImageFont

from pyqtree import Index

"""
Read a file with <tag_name, x, y> triples and compute an image representation 
for described points.

This script creates so-called "tiles": many small images with grid-like arrangement.
Tiles are well described in http://wiki.openstreetmap.org/wiki/Tiles.

This routine saves tiles according into folder parametrized by 
input date. This date means the lowest date of any post that
is used to compute tag similarity. This way, you can save
multiple maps (referring to multiple dates) and compare them.


Input parameters:
    1 - path to a tsv-file which describes points
    2 - path to a csv-file with additional information about points
    3 - maximum zoom level for created tiles
    4 - lower bound on a date of any post that is used to compute tag similarity.

Output:
    Writes output tiles to a directory `TILES_DIR_BASE` with appended posts date.
    Deletes everything in it beforehand.
    Tiles are named `x_y_z.png`, where `z` is the zoom level, `x` and `y` are
    tile coordinates (from 0 to 2**z - 1).


Example usage:
    python3 get_tiling.py tsne_output_example.tsv id_to_additional_info_example.csv 5 example
"""

TILES_DIR_BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tiles')

# Each tile is rendered in (256x256)*ANTIALIASING_SCALE size,
# and then downscaled with antialiasing.
# http://stackoverflow.com/questions/14350645/is-there-antialiasing-method-for-python-pil
ANTIALIASING_SCALE = 1
TILE_DIM = 256 * ANTIALIASING_SCALE
# SHIFT is used for ensuring that any geometry on the border of two tiles
# is drawn properly.
SHIFT = 10 * ANTIALIASING_SCALE
# Tiles are united in groups of METATILE_SIZE x METATILE_SIZE units.
METATILE_SIZE = 8
# The level, starting at which all tag names are shown, and number of shown tag 
# names per tile.
ZOOM_TEXT_SHOW = 7
TAGS_ANNOTATED_PER_TILE = 10

Point = namedtuple('Point', ['x', 'y'])


def get_tags_data(tsv_data_path, additional_data_path):
    with open(additional_data_path, 'r', newline='') as additional_info_file:
        additional_reader = csv.DictReader(additional_info_file)
        with open(tsv_data_path, 'r', newline='') as tsvfile:
            reader = csv.DictReader(tsvfile, delimiter='\t')
            tags = []
            for row, add_info in zip(reader, additional_reader):
                flat_addinfo = [(name, add_info[name]) for name in additional_reader.fieldnames]
                tags.append(Tag(float(row['x']), float(row['y']), *flat_addinfo))

            return tags

class Tag:

    def __init__(self, x, y, *additional_info):
        self.x = x
        self.y = y
        for field_name, field_val in additional_info:
            self.__dict__[field_name] = field_val


class Tiler:

    def set_extent(self, tags):
        self.max_x = max((tag.x for tag in tags)) + SHIFT
        self.min_x = min((tag.x for tag in tags)) - SHIFT

        self.max_y = max((tag.y for tag in tags)) + SHIFT
        self.min_y = min((tag.y for tag in tags)) - SHIFT

        self.origin = Point(self.min_x, self.min_y)
        max_size = max(self.max_x - self.min_x, self.max_y - self.min_y)
        self.map_size = max_size

        self.tile_size = [self.map_size / (1 << i) * METATILE_SIZE for i in range(20)]

        self.tag_to_normpos = dict()
        for tag in tags:
            x, y = tag.x, tag.y
            rel_x, rel_y = x - self.origin.x, y - self.origin.y
            norm_x, norm_y = rel_x / self.map_size, rel_y / self.map_size
            self.tag_to_normpos[tag.name] = (norm_x, norm_y)


    def set_bbox(self, tags):
        self.tag_spatial_index = Index(bbox=(self.min_x, self.min_y, self.max_x, self.max_y))
        for tag in tags:
            bbox = (tag.x, tag.y, tag.x, tag.y)
            self.tag_spatial_index.insert(tag, bbox)


    def set_postcount(self, tags):
        for tag in tags:
            tag.PostCount = int(getattr(tag, 'PostCount', -1))
        self.max_post_count = max(int(tag.PostCount) for tag in tags)


    def set_fonts(self):
        path_to_font = os.path.join(os.path.dirname(os.path.abspath(__file__)), './Verdana.ttf')
        self.fonts = [ImageFont.truetype(path_to_font, ANTIALIASING_SCALE * (25 - zoom * 2)) for zoom in range(8 + 1)]


    def __init__(self, tags):
        self.set_extent(tags)
        self.set_bbox(tags)
        self.set_postcount(tags)
        self.set_fonts()


    def search(self, name):
        return self.tag_to_normpos.get(name, '')


    def get_postcount_measure(self, tag):
        tag_count = tag.PostCount
        max_post_count = self.max_post_count
        return tag_count / max_post_count


    def get_tags_in_tile(self, meta_x, meta_y, zoom, with_shift):
        tile_size = self.tile_size[zoom]
        lower_left_corner = Point(self.origin.x + meta_x * tile_size,
                                  self.origin.y + meta_y * tile_size)

        shift = SHIFT if with_shift else 0
        tags_inside_tile = self.tag_spatial_index.intersect((lower_left_corner.x - shift, 
                                                             lower_left_corner.y - shift,
                                                             lower_left_corner.x + tile_size + shift, 
                                                             lower_left_corner.y + tile_size + shift))

        return tags_inside_tile


    def get_names_of_shown_tags(self, meta_x, meta_y, zoom):
        """
        Return the names of tags that we will show on the map.

        On low zoom levels, not all names are shown. 
        """
        if zoom >= ZOOM_TEXT_SHOW:
            # We know that all tag names will be shown anyway, so just return.
            return []

        tags_inside_tile = self.get_tags_in_tile(meta_x, meta_y, zoom, False)

        all_postcounts = sorted([(tag.PostCount, tag.name) for tag in tags_inside_tile])
        largest_tags = heapq.nlargest(TAGS_ANNOTATED_PER_TILE, all_postcounts)
        return {x[1] for x in largest_tags if x[0] > 0}


    def get_metatile(self, meta_x, meta_y, zoom):
        ''' 
        Get 8x8 rectangle of tiles, compute them at once. 
        This is faster than computing them one-by-one.

        `meta_x` and `meta_y` are coordinates of upper-left tile of the 
        generated metatile.
        '''
        meta_x /= METATILE_SIZE
        meta_y /= METATILE_SIZE

        img = Image.new('RGB', (TILE_DIM * METATILE_SIZE, 
            TILE_DIM * METATILE_SIZE), (240, 240, 240))
        draw = ImageDraw.Draw(img)

        tile_size = self.tile_size[zoom]
        lower_left_corner = Point(self.origin.x + meta_x * tile_size,
                                  self.origin.y + meta_y * tile_size)
        max_circle_rad = zoom * 1
        cnt_points = 0

        names_of_shown_tags = set()
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                names_of_shown_tags.update(self.get_names_of_shown_tags(meta_x + dx, meta_y + dy, zoom))

        # Match slightly more tags, so that circles from neighbouring tiles can be drawn partially.
        tags_inside_tile = self.get_tags_in_tile(meta_x, meta_y, zoom, True)


        def get_point_from_tag(tag):
            x, y = tag.x, tag.y

            # Get coordinates from tile origin.
            point_coords = Point(x - lower_left_corner.x, y - lower_left_corner.y)
            # Now scale to TILE_DIM.
            pnt = Point(point_coords.x / tile_size * TILE_DIM * METATILE_SIZE,
                        point_coords.y / tile_size * TILE_DIM * METATILE_SIZE)
            return pnt


        for tag in tags_inside_tile:
            pnt = get_point_from_tag(tag)

            # Heuristic formula for showing post counts by circle sizes.
            post_count_measure = self.get_postcount_measure(tag)
            circle_rad = max(0.5, max_circle_rad * post_count_measure)

            draw.ellipse([pnt.x - circle_rad, pnt.y - circle_rad,
                   pnt.x + circle_rad, pnt.y + circle_rad],
                   fill=(122, 176, 42))

            cnt_points += 1

        # Draw text after all circles, so that it is not overwritten.
        # (because I did not find any kind of z-index feature in PIL)
        for tag in tags_inside_tile:
            pnt = get_point_from_tag(tag)
            fill = (0, 0, 0)
            if zoom >= ZOOM_TEXT_SHOW or tag.name in names_of_shown_tags:
                draw.text(pnt, tag.name, fill=fill, font=self.fonts[zoom])

        del draw

        return img, cnt_points


def get_tile_dir(date_suffix):
    return '{}_{}'.format(TILES_DIR_BASE, date_suffix)


def prepare_tile_dir(tile_dir):
    try:
        shutil.rmtree(tile_dir)
    except FileNotFoundError:
        pass
    os.mkdir(tile_dir)


def render_tiles(img, meta_x, meta_y, tile_zoom, tile_dir):
    for dx in range(METATILE_SIZE):
        x = meta_x + dx
        if x >= 2 ** tile_zoom:
            break

        for dy in range(METATILE_SIZE):
            y = meta_y + dy
            if y >= 2 ** tile_zoom:
                break

            img_name = os.path.join(tile_dir, '{}_{}_{}.png'.format(x, y, tile_zoom))

            image_part = img.crop((dx * TILE_DIM, dy * TILE_DIM, 
                                    (dx + 1) * TILE_DIM, (dy + 1) * TILE_DIM))

            image_part = image_part.resize((TILE_DIM // ANTIALIASING_SCALE,
                                            TILE_DIM // ANTIALIASING_SCALE),
                                            resample=Image.LANCZOS)

            image_part.save(img_name, optimize=True)

    del img


def main():
    tsv_data_path = sys.argv[1]
    additional_data_path = sys.argv[2]
    max_tile_zoom = int(sys.argv[3])
    date_suffix = sys.argv[4]

    tile_dir = get_tile_dir(date_suffix)
    prepare_tile_dir(tile_dir)

    tiler = Tiler(get_tags_data(tsv_data_path, additional_data_path))
    pool = ThreadPoolExecutor()


    for tile_zoom in range(0, max_tile_zoom + 1):
        print('Generating zoom level =', tile_zoom)
        for meta_x in range(0, 1 << tile_zoom, METATILE_SIZE):
            for meta_y in range(0, 1 << tile_zoom, METATILE_SIZE):
                img, cnt_points = tiler.get_metatile(meta_x, meta_y, tile_zoom)
                pool.submit(render_tiles, img, meta_x, meta_y, tile_zoom, tile_dir)


    pool.shutdown(wait=True)


if __name__ == '__main__':
    main()
