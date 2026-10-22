"""Bits Decomposer Analyzer for Image Submissions."""

from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from .base_analyzer import SubprocessAnalyzer
from .pil_utils import PALETTE_NOTE, load_image_array

RGB_CHANNEL_THRESHOLD = 3
GRAYSCALE_DIMENSIONS = 2


class DecomposerAnalyzer(SubprocessAnalyzer):
    """Analyzer for bits decomposer."""

    name = "decomposer"
    display_order = 10
    accepts = frozenset({"image"})

    def get_results(self, password: str | None = None) -> dict[str, Any]:
        """Analyze an image submission using bits decomposition."""
        _ = password
        return self.get_frame_results(0)

    def get_frame_results(self, frame_index: int) -> dict[str, Any]:
        """Decompose one selected frame and save uniquely named plane images."""
        loaded = load_image_array(self.input_img, frame_index)
        if loaded.error is not None or loaded.array is None:
            return loaded.error or {"status": "error", "error": "Image could not be loaded."}
        converted = loaded.converted
        img_np = loaded.array
        with Image.open(self.input_img) as source:
            frame_count = getattr(source, "n_frames", 1)

        # Handle grayscale, RGB, RGBA, etc.
        channels = 1 if len(img_np.shape) == GRAYSCALE_DIMENSIONS else img_np.shape[2]

        channel_names = ["Red", "Green", "Blue", "Alpha"] if channels > 1 else ["Grayscale"]

        image_json = {}
        filename_prefix = f"gif_frame_{frame_index + 1:04d}_" if frame_index else ""

        # Add Superimposed RGB bit planes
        if channels >= RGB_CHANNEL_THRESHOLD:
            superimposed_json = []
            for bit in range(8):
                bit_mask = 1 << bit
                rgb_planes = [((img_np[..., c] & bit_mask) >> bit) * 255 for c in range(3)]
                rgb_image = np.stack(rgb_planes, axis=-1).astype(np.uint8)
                rgb_img = Image.fromarray(rgb_image, mode="RGB")
                img_name = f"{filename_prefix}superimposed_bit_{bit}.png"
                out_path = self.output_dir / img_name
                dl_path = Path(self.output_dir.name) / img_name
                superimposed_json.append("/image/" + str(dl_path))
                rgb_img.save(out_path)

            image_json["Superimposed"] = superimposed_json

        # Process individual channels
        for c in range(channels):
            channel_data = img_np[..., c] if channels > 1 else img_np
            channel_label = channel_names[c]
            channel_json = []
            for bit in range(8):
                bit_mask = 1 << bit
                bit_plane = ((channel_data & bit_mask) >> bit) * 255
                bit_img = Image.fromarray(bit_plane.astype(np.uint8), mode="L")
                img_name = f"{filename_prefix}{channel_label}_bit_{bit}.png"
                out_path = self.output_dir / img_name
                dl_path = Path(self.output_dir.name) / img_name
                channel_json.append("/image/" + str(dl_path))
                bit_img.save(out_path)
            image_json[channel_label] = channel_json

        output = {
            "status": "ok",
            "images": image_json,
            "frame_index": frame_index,
            "frame_count": frame_count,
        }
        if converted:
            output["note"] = PALETTE_NOTE

        return output
