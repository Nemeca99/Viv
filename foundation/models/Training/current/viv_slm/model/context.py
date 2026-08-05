"""Part 4 causal context model with token and position embeddings."""
from __future__ import annotations

import torch
from torch import Tensor, nn
from torch.nn import functional as F


class ContextLanguageModel(nn.Module):
    """A small causal character model for the Part 4 tutorial step.

    Each character gets a learned token vector.  Each position in the context
    window gets a learned position vector.  Their sum is passed through a
    lower-triangular, row-normalized matrix so position ``t`` averages its own
    representation and all representations before it, never future positions.
    A linear head converts the resulting 64-dimensional context vector into
    one next-character logit for every vocabulary character.
    """

    def __init__(
        self,
        vocab_size: int,
        *,
        context_length: int = 128,
        embedding_width: int = 64,
    ):
        super().__init__()
        if not isinstance(vocab_size, int) or vocab_size <= 0:
            raise ValueError("vocab_size_must_be_positive_integer")
        if not isinstance(context_length, int) or context_length <= 0:
            raise ValueError("context_length_must_be_positive_integer")
        if not isinstance(embedding_width, int) or embedding_width <= 0:
            raise ValueError("embedding_width_must_be_positive_integer")
        self.vocab_size = vocab_size
        self.context_length = context_length
        self.embedding_width = embedding_width
        self.token_embedding_table = nn.Embedding(vocab_size, embedding_width)
        self.position_embedding_table = nn.Embedding(context_length, embedding_width)
        self.register_buffer(
            "causal_mask",
            torch.tril(torch.ones(context_length, context_length)),
            persistent=True,
        )
        self.lm_head = nn.Linear(embedding_width, vocab_size)

    def _validate_ids(self, token_ids: Tensor) -> Tensor:
        if not isinstance(token_ids, Tensor) or token_ids.dtype not in (
            torch.uint8,
            torch.int8,
            torch.int16,
            torch.int32,
            torch.int64,
        ):
            raise TypeError("context_token_ids_must_be_integer_tensor")
        if token_ids.numel() and (
            int(token_ids.min()) < 0 or int(token_ids.max()) >= self.vocab_size
        ):
            raise ValueError("context_token_id_out_of_range")
        return token_ids.to(dtype=torch.long)

    def forward(self, input_ids: Tensor) -> Tensor:
        """Return next-character logits for every position in the input."""
        ids = self._validate_ids(input_ids)
        if ids.ndim != 2:
            raise ValueError("context_input_ids_must_be_rank_two")
        _, time = ids.shape
        if time <= 0 or time > self.context_length:
            raise ValueError("context_length_out_of_range")

        token_vectors = self.token_embedding_table(ids)
        position_ids = torch.arange(time, device=ids.device)
        position_vectors = self.position_embedding_table(position_ids)
        represented = token_vectors + position_vectors.unsqueeze(0)

        mask = self.causal_mask[:time, :time]
        weights = mask / mask.sum(dim=-1, keepdim=True)
        context_vectors = torch.einsum("ij,bjc->bic", weights, represented)
        return self.lm_head(context_vectors)

    def loss_and_accuracy(self, logits: Tensor, target_ids: Tensor) -> tuple[Tensor, Tensor]:
        targets = self._validate_ids(target_ids)
        if logits.shape[:-1] != targets.shape or logits.shape[-1] != self.vocab_size:
            raise ValueError("context_logits_target_shape_mismatch")
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
        """Sample a character from the causal context and append it repeatedly."""
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
            cropped = output[:, -self.context_length :]
            next_logits = self(cropped)[:, -1, :]
            probabilities = F.softmax(next_logits / temperature, dim=-1)
            sampled_ids = torch.multinomial(probabilities, num_samples=1, generator=generator)
            output = torch.cat((output, sampled_ids), dim=1)
        return output
