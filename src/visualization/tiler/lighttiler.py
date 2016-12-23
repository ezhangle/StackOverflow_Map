# -*- coding: utf-8 -*-

import os
import heapq

from PIL import Image, ImageDraw, ImageOps, ImageFont


from tiler.tiler import *


class LightTiler(Tiler):

    def set_fonts(self):
        path_to_font = os.path.join(os.path.dirname(os.path.abspath(__file__)), './Verdana.ttf')
        self.fonts = [ImageFont.truetype(path_to_font, ANTIALIASING_SCALE * (25 - zoom * 2)) for zoom in range(8 + 1)]

    def __init__(self, tags):
        super().__init__(tags)
        #self.set_fonts()


    def get_postcount_measure(self, tag):
        tag_count = tag.PostCount
        max_post_count = self.max_post_count
        return tag_count / max_post_count


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


