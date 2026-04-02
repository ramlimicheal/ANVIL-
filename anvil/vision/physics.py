from typing import Tuple, Dict, Optional

try:
    import cv2
    import numpy as np
    from scipy.optimize import curve_fit
    from scipy.special import erf
    HAS_VISION_DEPS = True
except ImportError:
    HAS_VISION_DEPS = False

class PhotonicVerifier:
    """
    ANVIL Photonic Verification Layer.
    Audits generated CSS by reverse-engineering the 3D lighting design
    via inverse-rendering equations on linearized Luminance tensors.
    """
    def __init__(self, ref_image, gen_image):
        if not HAS_VISION_DEPS:
            raise ImportError(
                "Vision dependencies required: pip install opencv-python numpy scipy"
            )
        # 1. Gamma Linearization to map pixels back to physical photons
        ref_lin = self._srgb_to_linear(ref_image)
        gen_lin = self._srgb_to_linear(gen_image)
        
        # 2. Extract Precise Photometric Luminance (Rec. 709)
        self.ref_l = self._extract_luminance(ref_lin)
        self.gen_l = self._extract_luminance(gen_lin)
        self.height, self.width = self.ref_l.shape

    def _srgb_to_linear(self, img: np.ndarray) -> np.ndarray:
        """Removes display gamma compression to measure raw irradiance."""
        img_norm = img.astype(np.float64) / 255.0
        linear = np.where(img_norm <= 0.04045, 
                          img_norm / 12.92, 
                          np.power((img_norm + 0.055) / 1.055, 2.4))
        return linear

    def _extract_luminance(self, linear_img: np.ndarray) -> np.ndarray:
        """Calculates true physical luminance [0.0 - 1.0]."""
        return (0.2126 * linear_img[:,:,2] + 
                0.7152 * linear_img[:,:,1] + 
                0.0722 * linear_img[:,:,0])

    # ---------------------------------------------------------
    # A. GLOBAL LIGHT SOURCE VECTOR (TENSOR CALCULUS)
    # ---------------------------------------------------------
    def extract_light_vector(self, L: np.ndarray) -> Tuple[float, float, float]:
        """Calculates the dominant Light Vector by analyzing dense optical flow."""
        # Low-pass filter removes high-frequency structural noise (text, 1px borders)
        blurred = cv2.GaussianBlur(L, (15, 15), 0)

        # Sobel operations for 1st-order spatial derivatives
        gx = cv2.Sobel(blurred, cv2.CV_64F, 1, 0, ksize=3)
        gy = cv2.Sobel(blurred, cv2.CV_64F, 0, 1, ksize=3)
        
        magnitude = np.hypot(gx, gy)
        
        # Isolate the sharpest luminance gradients (top 5%)
        # This targets structural shadows/highlights and ignores flat backgrounds
        threshold = np.percentile(magnitude, 95)
        mask = magnitude > threshold
        
        if not np.any(mask):
            return (0.0, 0.0, 0.0) # Ambient flat lighting
            
        # Magnitude-weighted mean directional vector
        weights = magnitude[mask]
        mean_x = np.average(gx[mask], weights=weights)
        mean_y = np.average(gy[mask], weights=weights)
        
        norm = np.hypot(mean_x, mean_y) + 1e-8
        
        # The unit vector points exactly toward the primary light source
        unit_x, unit_y = mean_x / norm, mean_y / norm
        angle = np.degrees(np.arctan2(unit_y, unit_x)) % 360
        
        return (unit_x, unit_y, angle)

    # ---------------------------------------------------------
    # B. DIFFUSE FALLOFF (ERF CONVOLUTION / GAUSSIAN DECAY)
    # ---------------------------------------------------------
    @staticmethod
    def _erf_decay(x, a, b, mu, sigma):
        """Math model: CSS box-shadow off a straight edge is an Error Function."""
        return b + (a / 2.0) * (1.0 - erf((x - mu) / (sigma * np.sqrt(2))))

    @staticmethod
    def _gaussian_decay(x, a, x0, sigma, c):
        """Math model: CSS radial-gradient or point-light bloom."""
        return c + a * np.exp(-((x - x0)**2) / (2 * sigma**2))

    def validate_diffuse_falloff(self, is_radial: bool = False) -> float:
        """
        Casts a 1D pixel ray from the glow epicenter and fits the decay curve.
        Returns the R^2 fitness score of the generated CSS against physical reality.
        """
        # Auto-locate the maximum luminance epicenter
        _, _, _, max_loc = cv2.minMaxLoc(cv2.GaussianBlur(self.ref_l, (21, 21), 0))
        start_x, start_y = max_loc
        
        # Raycast 50px outward
        ray_length = min(50, self.width - start_x - 1)
        if ray_length < 10: return 1.0 

        ref_ray = self.ref_l[start_y, start_x : start_x + ray_length]
        gen_ray = self.gen_l[start_y, start_x : start_x + ray_length]
        x_data = np.arange(ray_length)
        
        decay_model = self._gaussian_decay if is_radial else self._erf_decay
        
        # Initial parameters: [Amplitude, Baseline/Offset, Midpoint, Spread(Sigma)]
        p0 = [np.ptp(ref_ray), np.min(ref_ray), ray_length/4.0, max(1.0, ray_length/4.0)]
        
        try:
            # Fit the True Reference Ray to extract theoretical physical parameters
            popt_ref, _ = curve_fit(decay_model, x_data, ref_ray, p0=p0, maxfev=2000)
            
            # Predict the theoretical ideal curve based on reference physics
            ideal_curve = decay_model(x_data, *popt_ref)
            
            # Calculate R^2 fitness of the Generated AI CSS against the theoretical ideal
            ss_res = np.sum((gen_ray - ideal_curve) ** 2)
            ss_tot = np.sum((gen_ray - np.mean(ideal_curve)) ** 2)
            
            if ss_tot == 0: return 0.0 # Flat color where gradient is expected
            
            r2 = 1.0 - (ss_res / ss_tot)
            return max(0.0, float(r2))
            
        except RuntimeError:
            return 0.0 # Curve fit failed to converge (AI hallucinated a flat linear-gradient)

    # ---------------------------------------------------------
    # C. EDGE SPECULAR REFLECTION (FRESNEL RIM LIGHTING)
    # ---------------------------------------------------------
    def verify_specular_edges(self, light_vector: Tuple[float, float]) -> float:
        """Validates specular highlights via Laplacian mapping & Lambertian dot products."""
        lx, Ly = light_vector
        if lx == 0 and Ly == 0: return 1.0 

        # 1. Edge Normal Mapping (Sharp boundaries)
        ref_edges = np.abs(cv2.Laplacian(self.ref_l, cv2.CV_64F))
        gx = cv2.Sobel(self.ref_l, cv2.CV_64F, 1, 0, ksize=3)
        gy = cv2.Sobel(self.ref_l, cv2.CV_64F, 0, 1, ksize=3)
        
        norm = np.hypot(gx, gy) + 1e-8
        nx, ny = gx / norm, gy / norm # Surface Unit Normals
        
        # 2. Lambertian Dot Product Map (Normal • Light)
        dot_product = (nx * lx) + (ny * Ly)
        
        # 3. Specular Mask: Sharp edges perfectly facing the light source (Rim Light Zones)
        specular_mask = (dot_product > 0.85) & (ref_edges > 0.1) & (self.ref_l > 0.8)
        
        if not np.any(specular_mask):
            return 1.0 # No rim light expected in this design
            
        # 4. Verify AI wrote CSS that illuminated these exact pixels
        ref_rim_intensity = np.mean(self.ref_l[specular_mask])
        gen_rim_intensity = np.mean(self.gen_l[specular_mask])
        
        # If generated UI missed the 1px inset shadow, gen_rim_intensity plunges
        error = np.abs(ref_rim_intensity - gen_rim_intensity)
        return float(np.clip(1.0 - error, 0.0, 1.0))

    def evaluate(self) -> Dict[str, float]:
        """Master Execution Sequence"""
        ref_vx, ref_vy, ref_angle = self.extract_light_vector(self.ref_l)
        gen_vx, gen_vy, gen_angle = self.extract_light_vector(self.gen_l)
        
        # A. Vector Alignment: Cosine Similarity normalized to [0, 1]
        cosine_sim = (ref_vx * gen_vx) + (ref_vy * gen_vy)
        vector_score = float(np.clip((cosine_sim + 1.0) / 2.0, 0.0, 1.0))
        
        # B. Gaussian/Erf Decay Fit
        decay_score = self.validate_diffuse_falloff()
        
        # C. Specular Preservation
        specular_score = self.verify_specular_edges((ref_vx, ref_vy))
        
        # Composite Rigid Physics Score
        overall = (vector_score * 0.4) + (decay_score * 0.4) + (specular_score * 0.2)
        
        return {
            "TotalPhysics": float(overall),
            "VectorScore": float(vector_score),
            "BloomR2": decay_score,
            "SpecularMatch": specular_score,
            "Diagnostics": {"RefAngle": float(ref_angle), "GenAngle": float(gen_angle)}
        }
