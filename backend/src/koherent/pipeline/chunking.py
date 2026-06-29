from dataclasses import dataclass
from koherent.ai.base import TranscriptWord
from itertools import groupby

@dataclass(frozen=True)
class ChunkText:
    index: int
    content: str
    start_ms: int
    end_ms: int

def chunk_transcript(words: list[TranscriptWord], chunk_ms: int = 30_000) -> list[ChunkText]:
   
    chunks: list[ChunkText] = []
    
    for index, (_bucket, bucket_words) in enumerate(groupby(words, key=lambda w: w.start_ms//chunk_ms)):
        group = list(bucket_words)
        chunks.append(
            ChunkText(
                index=index,
                content = " ".join(w.word for w in group),
                start_ms = group[0].start_ms,
                end_ms = group[-1].end_ms
            )
        )  

    return chunks

