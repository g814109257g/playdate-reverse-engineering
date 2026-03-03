#!/usr/bin/env python3
# PDI to PNG converter
# PDI docs: https://github.com/jaames/playdate-reverse-engineering/blob/main/formats/pdi.md

from struct import unpack, pack
from zlib import compress, crc32, decompress
from argparse import ArgumentParser

PDI_IDENT = b'Playdate IMG'
PNG_SIGNATURE = b'\x89PNG\r\n\x1a\n'

def png_chunk(chunk_type, data):
  chunk = chunk_type + data
  return pack('>I', len(data)) + chunk + pack('>I', crc32(chunk) & 0xffffffff)

def write_png(path, width, height, rows, has_alpha):
  # color type: 0 = grayscale, 4 = grayscale+alpha
  color_type = 4 if has_alpha else 0
  ihdr = pack('>IIBBBBB', width, height, 8, color_type, 0, 0, 0)

  # build raw image data: filter byte (0=none) + row pixels
  raw = bytearray()
  for row in rows:
    raw.append(0)  # filter: none
    raw.extend(row)

  with open(path, 'wb') as f:
    f.write(PNG_SIGNATURE)
    f.write(png_chunk(b'IHDR', ihdr))
    f.write(png_chunk(b'IDAT', compress(bytes(raw))))
    f.write(png_chunk(b'IEND', b''))

def read_cell(data, offset):
  clip_width, clip_height, stride, clip_left, clip_right, clip_top, clip_bottom, flags = \
    unpack('<8H', data[offset:offset + 16])
  offset += 16

  has_alpha = (flags & 0x3) > 0

  # read color bitmap (1-bit, 0=black 1=white)
  color_size = stride * clip_height
  color_data = data[offset:offset + color_size]
  offset += color_size

  # read alpha bitmap if present (1-bit, 0=transparent 1=opaque)
  alpha_data = None
  if has_alpha:
    alpha_data = data[offset:offset + color_size]
    offset += color_size

  # reconstruct full image dimensions
  full_width = clip_left + clip_width + clip_right
  full_height = clip_top + clip_height + clip_bottom

  # build pixel rows
  rows = []
  for y in range(full_height):
    if has_alpha:
      row = bytearray(full_width * 2)  # grayscale + alpha per pixel
    else:
      row = bytearray(b'\xff' * full_width)  # default white

    cy = y - clip_top
    if 0 <= cy < clip_height:
      row_offset = cy * stride
      for x in range(clip_width):
        byte_index = row_offset + (x // 8)
        bit_index = 7 - (x % 8)
        color_bit = (color_data[byte_index] >> bit_index) & 1
        color = 255 if color_bit else 0
        px = clip_left + x

        if has_alpha:
          alpha_bit = (alpha_data[byte_index] >> bit_index) & 1
          alpha = 255 if alpha_bit else 0
          row[px * 2] = color
          row[px * 2 + 1] = alpha
        else:
          row[px] = color

    rows.append(row)

  return full_width, full_height, rows, has_alpha

def convert_pdi(input_path, output_path):
  with open(input_path, 'rb') as f:
    data = f.read()

  # verify ident
  ident = data[0:12]
  if ident != PDI_IDENT:
    raise ValueError(f'Not a valid PDI file (got ident {ident!r})')

  flags = unpack('<I', data[12:16])[0]
  is_compressed = (flags & 0x80000000) > 0

  offset = 16

  if is_compressed:
    decompressed_size, width, height, reserved = unpack('<4I', data[offset:offset + 16])
    offset += 16
    image_data = decompress(data[offset:])
  else:
    image_data = data[offset:]

  full_width, full_height, rows, has_alpha = read_cell(image_data, 0)
  write_png(output_path, full_width, full_height, rows, has_alpha)
  print(f'Saved {output_path} ({full_width}x{full_height})')

if __name__ == '__main__':
  parser = ArgumentParser(description='Convert Playdate .pdi images to .png')
  parser.add_argument('input', help='Input .pdi file path')
  parser.add_argument('-o', '--output', help='Output .png file path (default: input with .png extension)')
  args = parser.parse_args()

  output = args.output
  if not output:
    if args.input.lower().endswith('.pdi'):
      output = args.input[:-4] + '.png'
    else:
      output = args.input + '.png'

  convert_pdi(args.input, output)
