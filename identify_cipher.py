import os
import pathlib
import sys
import time

import cv2
import numpy as np
import tesserocr
from PIL import Image
from tesserocr import OEM, PSM, RIL, PyTessBaseAPI

if len(sys.argv) != 2:
    print("[ERROR] Invalid amount or no arguments")
    print("Example usage: python find_cipher.py image.png")
    exit(1)

image_path = sys.argv[1]

if not os.path.exists(image_path):
    print("[ERROR] Could not find image:", image_path)
    exit(1)

BASE_PATH = pathlib.Path(__file__).resolve().parent.absolute()
# TESSDATA_PATH = "/usr/share/tessdata"
TESSDATA_PATH = "{}/models/tessdata".format(BASE_PATH)
CIPHER_LANGUAGES = sorted(
    [
        f.replace(".traineddata", "")
        for f in os.listdir(TESSDATA_PATH)
        if "traineddata" in f
    ]
)


def preprocess_image(
    image_path,
    grayscale=True,
    remove_noise=True,
    thresholding=True,
    auto_crop=True,
    debug=False
):
    # TODO: need to add borders if they're missing, else we get 0% confidence because of no padding
    image = cv2.imread(image_path)
    if debug:
        cv2.imshow('original', image)
        cv2.waitKey(0)

    # Grayscale
    if not grayscale:
        process_image = image.copy()
    else:
        process_image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        if debug:
            cv2.imshow('grayscale', process_image)
            cv2.waitKey(0)

    # Remove noise
    if remove_noise:
        process_image = cv2.medianBlur(process_image, 5)
        if debug:
            cv2.imshow('median_blur', process_image)
            cv2.waitKey(0)

    # Thresholding
    if thresholding:
        process_image = cv2.threshold(process_image, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
        if debug:
            cv2.imshow('thresholding', process_image)
            cv2.waitKey(0)

    # Auto crop
    if auto_crop:
        # Let's prepare for cropping the image to the text

        # Reverse the color with thresholding
        threshold = cv2.threshold(process_image, 0, 255, cv2.THRESH_OTSU | cv2.THRESH_BINARY_INV)[1]
        if debug:
            cv2.imshow('auto crop - threshold - invert', threshold)
            cv2.waitKey(0)

        # Dilate
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 3))
        dilation = cv2.dilate(threshold, kernel, iterations=1)
        if debug:
            cv2.imshow('auto crop - dilation', dilation)
            cv2.waitKey(0)

        # Find the contour of the text
        contours = cv2.findContours(dilation, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)[0]
        chosen_contour = 0
        contour = contours[chosen_contour]

        if debug:
            print("Found {} contours".format(len(contours)))
            # Draw all the contours
            contours_image = image.copy()
            cv2.drawContours(contours_image, contours, -1, (0, 255, 0), 1)
            cv2.imshow('auto crop - all_contours', contours_image)
            cv2.waitKey(0)

        if debug:
            # Draw the chosen contour
            contour_image = image.copy()
            cv2.drawContours(contour_image, contours, chosen_contour, (0, 255, 0), 1)
            cv2.imshow('auto crop - chosen contour', contour_image)
            cv2.waitKey(0)


        # Crop the image to the contour and return it
        x, y, w, h = cv2.boundingRect(contour)
        process_image = process_image[y : y + h, x : x + w]

    if debug:
        cv2.imshow('final', process_image)
        cv2.waitKey(0)
        cv2.destroyAllWindows()

    return process_image


"""
PSM:
Page segmentation modes.

 0  OSD_ONLY   Orientation and script detection (OSD) only.
 1  AUTO_OSD   Automatic page segmentation with OSD.
 2  AUTO_ONLY  Automatic page segmentation, but no OSD, or OCR.
 3  AUTO       Fully automatic page segmentation, but no OSD. (Default)
 4  SINGLE_COLUMN  Assume a single column of text of variable sizes.
 5  SINGLE_BLOCK_VERT_TEXT  Assume a single uniform block of vertically aligned text.
 6  SINGLE_COLUMN  Assume a single uniform block of text.
 7  SINGLE_LINE    Treat the image as a single text line.
 8  SINGLE_WORD    Treat the image as a single word.
 9  CIRCLE_WORD    Treat the image as a single word in a circle.
 10  SINGLE_CHAR   Treat the image as a single character.
 11  SPARSE_TEXT      Sparse text. Find as much text as possible in no particular order.
 12  SPARSE_TEXT_OSD  Sparse text with OSD.
 13  RAW_LINE         Raw line. Treat the image as a single text line, bypassing hacks that are Tesseract-specific.
"""
PSM_MODE = PSM.SINGLE_LINE

# TODO: loop through each contour and check the confidence of each one
image = preprocess_image(
    image_path,
    grayscale=True,
    remove_noise=False,
    thresholding=True,
    auto_crop=True,
    debug=False,
)

# Transform OpenCV image to a Pillow image for tesseract
image = Image.fromarray(image)

cipher_results = {}
for cipher_language in CIPHER_LANGUAGES:
    start = time.process_time()
    print("Checking:", cipher_language, end=" = ")

    with PyTessBaseAPI(path=TESSDATA_PATH, lang=cipher_language, psm=PSM_MODE) as api:
        api.SetImage(image)
        text = api.GetUTF8Text().strip()
        # TODO: Get confidence for each character / word?
        word_count = len(api.AllWordConfidences())
        confidence = api.MeanTextConf()
        print("{}%".format(confidence), end="")

    cipher_results[cipher_language] = {
        "text": text,
        "confidence": confidence,
        "word_count": word_count,
    }

    end = time.process_time() - start
    print(", took {} seconds".format(round(end, 4)))

# Sort the by confidence
cipher_results = {
    k: v
    for k, v in sorted(
        cipher_results.items(), reverse=True, key=lambda item: item[1]["confidence"]
    )
}

print("=" * 32)
print("Top ciphers:")
for index, cipher in enumerate(cipher_results):
    result = cipher_results[cipher]
    print(
        index + 1, "{}%".format(result["confidence"]), cipher, result["text"], sep="\t"
    )

print("=" * 32)
