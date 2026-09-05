# RAG Decision Record

## Decision

This project uses keyword-based document search instead of a vector database.

## Reason

The project's document collection is intentionally small and consists of local text files. A simple keyword search is sufficient to retrieve relevant information for debate agents.

Using a vector database would introduce additional complexity, storage requirements, and embedding generation without providing significant benefits for the current project scope.

## Future Upgrade

If the document collection becomes much larger or users begin asking paraphrased questions that keyword search cannot answer effectively, the retrieval system can be upgraded to use:

- FAISS (local vector database)
- Sentence-Transformers (local embedding model)

Both of these solutions are free and run locally without requiring paid APIs.

## Conclusion

For the current AI Debate Arena, keyword search provides a simpler, faster, and fully free solution while meeting all project requirements.