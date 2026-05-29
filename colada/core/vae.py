# -*- coding: utf-8 -*-
"""
Autoencoder Variacional (VAE) convolucional para COLADA
========================================================

Implementa un VAE con encoder y decoder convolucionales, diseñado para
procesar parches de terreno (stacks multibanda) y aprender una representación
latente. Incluye Dropout2d en el encoder para regularización.

Arquitectura:
- Encoder: capas convolucionales con stride=2, BatchNorm, ReLU, Dropout2d.
- Espacio latente: dos capas fully connected para mu y logvar.
- Decoder: capas convolucionales transpuestas con BatchNorm, ReLU y Sigmoid final.

Las dimensiones de las capas se calculan automáticamente a partir del tamaño
del parche (tamanio_parche) y el número de capas necesario para reducir hasta
un tamaño mínimo de 4x4.
"""

import math
import torch
import torch.nn as nn
from typing import Tuple, Optional

# Importar constantes desde la configuración central
from ...config import VAE_IN_CHANNELS, VAE_LATENT_DIM, VAE_FEATURES, TAMANO_PARCHE


class AutoencoderVariacional(nn.Module):
    """
    Autoencoder Variacional convolucional.

    El encoder reduce la dimensión espacial mediante convoluciones con stride=2
    hasta alcanzar un tamaño mínimo de 4x4. Luego se aplanan las características
    y se proyectan a un espacio latente (mu, logvar). El decoder realiza la
    operación inversa con convoluciones transpuestas.

    Attributes:
        in_channels (int): Número de bandas de entrada.
        latent_dim (int): Dimensión del vector latente.
        features (int): Número base de filtros en la primera capa.
        tamanio_parche (int): Tamaño del parche cuadrado (píxeles).
        n_layers (int): Número de capas convolucionales del encoder.
        enc_out_size (int): Tamaño espacial de salida del encoder (antes de aplanar).
        enc_out_channels (int): Número de canales de salida del encoder.
        encoder_conv (nn.Sequential): Capas convolucionales del encoder.
        fc_mu (nn.Linear): Capa fully connected para la media.
        fc_logvar (nn.Linear): Capa fully connected para la log-varianza.
        decoder_input (nn.Linear): Capa que proyecta del espacio latente al tensor.
        decoder_conv (nn.Sequential): Capas convolucionales transpuestas del decoder.
    """

    def __init__(
        self,
        in_channels: Optional[int] = None,
        latent_dim: Optional[int] = None,
        features: Optional[int] = None,
        tamanio_parche: Optional[int] = None,
    ) -> None:
        """
        Inicializa el VAE con los parámetros especificados o los valores por defecto.

        Args:
            in_channels: Número de bandas de entrada (por defecto VAE_IN_CHANNELS).
            latent_dim: Dimensión del espacio latente (por defecto VAE_LATENT_DIM).
            features: Número base de filtros (por defecto VAE_FEATURES).
            tamanio_parche: Tamaño del parche cuadrado (por defecto TAMANO_PARCHE).
        """
        super().__init__()

        # Asignar valores por defecto desde config
        if in_channels is None:
            in_channels = VAE_IN_CHANNELS
        if latent_dim is None:
            latent_dim = VAE_LATENT_DIM
        if features is None:
            features = VAE_FEATURES
        if tamanio_parche is None:
            tamanio_parche = TAMANO_PARCHE

        # Validar parámetros
        if in_channels <= 0:
            raise ValueError(f"in_channels debe ser > 0, recibido {in_channels}")
        if latent_dim <= 0:
            raise ValueError(f"latent_dim debe ser > 0, recibido {latent_dim}")
        if features <= 0:
            raise ValueError(f"features debe ser > 0, recibido {features}")
        if tamanio_parche < 32:
            raise ValueError(f"tamanio_parche debe ser >= 32, recibido {tamanio_parche}")

        self.in_channels = in_channels
        self.latent_dim = latent_dim
        self.features = features
        self.tamanio_parche = tamanio_parche

        # Calcular número de capas convolucionales para reducir a 4x4
        final_min = 4
        self.n_layers = max(1, int(math.log2(tamanio_parche / final_min)))
        self.enc_out_size = tamanio_parche // (2 ** self.n_layers)

        # ------------------------------------------------------------------
        # Encoder convolucional con Dropout2d
        # ------------------------------------------------------------------
        encoder_layers = []
        in_ch = in_channels
        for i in range(self.n_layers):
            out_ch = features * (2 ** i)
            encoder_layers.extend([
                nn.Conv2d(in_ch, out_ch, kernel_size=4, stride=2, padding=1),
                nn.BatchNorm2d(out_ch),
                nn.ReLU(inplace=True),
                nn.Dropout2d(p=0.1),               # Regularización
            ])
            in_ch = out_ch

        self.encoder_conv = nn.Sequential(*encoder_layers)

        self.enc_out_channels = features * (2 ** (self.n_layers - 1)) if self.n_layers > 0 else features

        # Capas fully connected para la distribución latente
        flat_dim = self.enc_out_channels * self.enc_out_size ** 2
        self.fc_mu = nn.Linear(flat_dim, latent_dim)
        self.fc_logvar = nn.Linear(flat_dim, latent_dim)

        # ------------------------------------------------------------------
        # Decoder convolucional transpuesto
        # ------------------------------------------------------------------
        self.decoder_input = nn.Linear(latent_dim, flat_dim)

        decoder_layers = []
        in_ch = self.enc_out_channels
        for i in range(self.n_layers - 1, 0, -1):
            out_ch = features * (2 ** (i - 1))
            decoder_layers.extend([
                nn.ConvTranspose2d(in_ch, out_ch, kernel_size=4, stride=2, padding=1),
                nn.BatchNorm2d(out_ch),
                nn.ReLU(inplace=True),
            ])
            in_ch = out_ch

        # Última capa: reconstrucción y activación sigmoide (rango [0,1])
        decoder_layers.append(
            nn.ConvTranspose2d(in_ch, in_channels, kernel_size=4, stride=2, padding=1)
        )
        decoder_layers.append(nn.Sigmoid())

        self.decoder_conv = nn.Sequential(*decoder_layers)

    def encode(self, x: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Codifica la entrada en los parámetros de la distribución latente.

        Args:
            x: Tensor de entrada (batch, canales, alto, ancho).

        Returns:
            (mu, logvar) donde mu y logvar son tensores de forma (batch, latent_dim).
        """
        h = self.encoder_conv(x)
        h = h.view(h.size(0), -1)  # Aplanar
        mu = self.fc_mu(h)
        logvar = self.fc_logvar(h)
        return mu, logvar

    def reparameterize(self, mu: torch.Tensor, logvar: torch.Tensor) -> torch.Tensor:
        """
        Aplica el truco de reparametrización para muestrear z ~ N(mu, exp(logvar)).

        Args:
            mu: Media de la distribución.
            logvar: Log-varianza de la distribución.

        Returns:
            Tensor z muestreado (batch, latent_dim).
        """
        std = torch.exp(0.5 * logvar)
        eps = torch.randn_like(std)
        return mu + eps * std

    def decode(self, z: torch.Tensor) -> torch.Tensor:
        """
        Decodifica un vector latente en una reconstrucción.

        Args:
            z: Tensor de forma (batch, latent_dim).

        Returns:
            Tensor reconstruido (batch, canales, alto, ancho) con valores en [0,1].
        """
        h = self.decoder_input(z)
        h = h.view(h.size(0), self.enc_out_channels, self.enc_out_size, self.enc_out_size)
        return self.decoder_conv(h)

    def forward(self, x: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Paso forward completo: encode -> reparameterize -> decode.

        Args:
            x: Tensor de entrada (batch, canales, alto, ancho).

        Returns:
            (reconstrucción, mu, logvar)
        """
        mu, logvar = self.encode(x)
        z = self.reparameterize(mu, logvar)
        recon = self.decode(z)
        return recon, mu, logvar