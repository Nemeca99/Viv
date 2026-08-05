"""The requested one-character-context bigram language model."""
from __future__ import annotations

import torch
from torch import Tensor, nn
from torch.nn import functional as F


class BigramLanguageModel(nn.Module):
    """A dense ``vocab_size x vocab_size`` next-character logits table.

    Row ``i`` contains the logits for the next character after input character
    ``i``.  Softmax is applied only when probabilities are needed for sampling.
    """

    def __init__(self, vocab_size: int):
        super().__init__()
        if not isinstance(vocab_size, int) or vocab_size <= 0:
            raise ValueError("vocab_size_must_be_positive_integer")
        self.vocab_size = vocab_size
        self.logits_table = nn.Parameter(torch.zeros(vocab_size, vocab_size))

    def _validate_ids(self, token_ids: Tensor) -> Tensor:
        if not isinstance(token_ids, Tensor) or token_ids.dtype not in (
            torch.int8,
            torch.int16,
            torch.int32,
            torch.int64,
        ):
            raise TypeError("bigram_token_ids_must_be_integer_tensor")
        if token_ids.numel() and (
            int(token_ids.min()) < 0 or int(token_ids.max()) >= self.vocab_size
        ):
            raise ValueError("bigram_token_id_out_of_range")
        return token_ids.to(dtype=torch.long)

    def forward(self, input_ids: Tensor) -> Tensor:
        """Return one logits row for every input position."""
        ids = self._validate_ids(input_ids)
        return self.logits_table[ids]

    def loss_and_accuracy(self, logits: Tensor, target_ids: Tensor) -> tuple[Tensor, Tensor]:
        targets = self._validate_ids(target_ids)
        if logits.shape[:-1] != targets.shape or logits.shape[-1] != self.vocab_size:
            raise ValueError("bigram_logits_target_shape_mismatch")
        loss = F.cross_entropy(logits.reshape(-1, self.vocab_size), targets.reshape(-1))
        accuracy = (logits.argmax(dim=-1) == targets).to(dtype=torch.float32).mean()
        return loss, accuracy

    @torch.no_grad()
    def generate(
        self,
        context_ids: Tensor,
        *,
        max_new_tokens: int,
        temperature: float = 1.0,
        generator: torch.Generator | None = None,
    ) -> Tensor:
        """Sample one next character, append it, and repeat."""
        if max_new_tokens < 0:
            raise ValueError("max_new_tokens_must_not_be_negative")
        if temperature <= 0:
            raise ValueError("temperature_must_be_positive")
        output = self._validate_ids(context_ids)
        if output.ndim == 1:
            output = output.unsqueeze(0)
        if output.ndim != 2 or output.shape[1] == 0:
            raise ValueError("generation_context_must_be_nonempty_rank_two")
        for _ in range(max_new_tokens):
            next_logits = self(output[:, -1:])[:, -1, :]
            probabilities = F.softmax(next_logits / temperature, dim=-1)
            sampled_ids = torch.multinomial(probabilities, num_samples=1, generator=generator)
            output = torch.cat((output, sampled_ids), dim=1)
        return output
