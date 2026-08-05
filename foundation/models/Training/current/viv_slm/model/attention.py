"""Part 5: one learned scaled causal self-attention head."""
from __future__ import annotations

import math

import torch
from torch import Tensor, nn
from torch.nn import functional as F


class CausalSelfAttentionHead(nn.Module):
    """One head that learns query, key, and value projections."""

    def __init__(self, embedding_width: int, head_size: int, context_length: int):
        super().__init__()
        if min(embedding_width, head_size, context_length) <= 0:
            raise ValueError("attention_dimensions_must_be_positive")
        self.embedding_width = embedding_width
        self.head_size = head_size
        self.context_length = context_length
        self.key = nn.Linear(embedding_width, head_size, bias=False)
        self.query = nn.Linear(embedding_width, head_size, bias=False)
        self.value = nn.Linear(embedding_width, head_size, bias=False)
        self.scale = head_size ** -0.5
        self.register_buffer(
            "causal_mask",
            torch.tril(torch.ones(context_length, context_length)),
            persistent=True,
        )

    def forward(self, represented: Tensor) -> tuple[Tensor, Tensor]:
        if represented.ndim != 3 or represented.shape[-1] != self.embedding_width:
            raise ValueError("attention_representation_shape_mismatch")
        _, time, _ = represented.shape
        if time <= 0 or time > self.context_length:
            raise ValueError("attention_context_length_out_of_range")

        # Every token produces a query, key, and value vector.
        keys = self.key(represented)
        queries = self.query(represented)
        values = self.value(represented)

        # Scaled dot-product attention keeps scores in a manageable range.
        scores = queries @ keys.transpose(-2, -1)
        scores = scores * self.scale

        # Future positions become -inf; softmax turns them into zero weight.
        mask = self.causal_mask[:time, :time]
        scores = scores.masked_fill(mask == 0, float("-inf"))
        weights = F.softmax(scores, dim=-1)
        output = weights @ values
        return output, weights


class SelfAttentionLanguageModel(nn.Module):
    """Part 4 embeddings plus one learned causal self-attention head."""

    def __init__(
        self,
        vocab_size: int,
        *,
        context_length: int = 128,
        embedding_width: int = 64,
        head_size: int = 64,
    ):
        super().__init__()
        if not isinstance(vocab_size, int) or vocab_size <= 0:
            raise ValueError("vocab_size_must_be_positive_integer")
        if min(context_length, embedding_width, head_size) <= 0:
            raise ValueError("attention_model_dimensions_must_be_positive")
        self.vocab_size = vocab_size
        self.context_length = context_length
        self.embedding_width = embedding_width
        self.head_size = head_size
        self.token_embedding_table = nn.Embedding(vocab_size, embedding_width)
        self.position_embedding_table = nn.Embedding(context_length, embedding_width)
        self.head = CausalSelfAttentionHead(
            embedding_width,
            head_size,
            context_length,
        )
        self.lm_head = nn.Linear(head_size, vocab_size)

    def _validate_ids(self, token_ids: Tensor) -> Tensor:
        if not isinstance(token_ids, Tensor) or token_ids.dtype not in (
            torch.uint8,
            torch.int8,
            torch.int16,
            torch.int32,
            torch.int64,
        ):
            raise TypeError("attention_token_ids_must_be_integer_tensor")
        if token_ids.numel() and (
            int(token_ids.min()) < 0 or int(token_ids.max()) >= self.vocab_size
        ):
            raise ValueError("attention_token_id_out_of_range")
        return token_ids.to(dtype=torch.long)

    def forward(
        self,
        input_ids: Tensor,
        *,
        return_attention: bool = False,
    ) -> Tensor | tuple[Tensor, Tensor]:
        ids = self._validate_ids(input_ids)
        if ids.ndim != 2:
            raise ValueError("attention_input_ids_must_be_rank_two")
        _, time = ids.shape
        if time <= 0 or time > self.context_length:
            raise ValueError("attention_context_length_out_of_range")

        token_vectors = self.token_embedding_table(ids)
        position_ids = torch.arange(time, device=ids.device)
        position_vectors = self.position_embedding_table(position_ids)
        represented = token_vectors + position_vectors.unsqueeze(0)
        attended, weights = self.head(represented)
        logits = self.lm_head(attended)
        if return_attention:
            return logits, weights
        return logits

    def loss_and_accuracy(self, logits: Tensor, target_ids: Tensor) -> tuple[Tensor, Tensor]:
        targets = self._validate_ids(target_ids)
        if logits.shape[:-1] != targets.shape or logits.shape[-1] != self.vocab_size:
            raise ValueError("attention_logits_target_shape_mismatch")
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
