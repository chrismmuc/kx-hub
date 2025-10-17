const zlib = require('zlib');

/**
 * INPUT (event):
 * {
 *   embeddingsS3Key: "embeddings/2025-10-10.parquet|ndjson|jsonl", // simplified for stub
 *   ids: ["id1","id2",...],     // parallel to vectors (if not reading from file)
 *   vectors: [[...],[...]],     // optional inline for small tests
 *   top_k: 5,
 *   min_score: 0.8,
 *   method: "cosine-numpy|faiss" // overrides env/config if set
 * }
 *
 * ENV:
 *   SIMILARITY_METHOD = "cosine-numpy" | "faiss"
 *   (Reading config/settings.yml is TODO in this stub; pass method via event for now.)
 */

function l2norm(vec){
  let sum = 0.0;
  for (let i=0;i<vec.length;i++) sum += vec[i]*vec[i];
  return Math.sqrt(sum);
}
function normalize(matrix){
  return matrix.map(v => {
    const n = l2norm(v) || 1.0;
    return v.map(x => x / n);
  });
}
function cosineTopK(normed, ids, top_k=5, min_score=0.0){
  const n = normed.length;
  const results = {};
  for (let i=0;i<n;i++){
    const sims = new Array(n);
    for (let j=0;j<n;j++){
      if (i===j){ sims[j] = -1; continue; }
      let dot = 0.0;
      const a = normed[i], b = normed[j];
      for (let k=0;k<a.length;k++) dot += a[k]*b[k];
      sims[j] = dot;
    }
    // top-k
    const idx = Array.from({length:n}, (_,j)=>j).sort((a,b)=>sims[b]-sims[a]).slice(0, top_k);
    const filtered = idx.filter(j => sims[j] >= min_score).map(j => ({ id: ids[j], score: +sims[j].toFixed(6) }));
    results[ids[i]] = filtered;
  }
  return results;
}

exports.handler = async (event) => {
  const method = (event.method || process.env.SIMILARITY_METHOD || "cosine-numpy").toLowerCase();
  const ids = event.ids || [];
  const vectors = event.vectors || []; // for stub testing; real impl should read from S3 (parquet/ndjson)
  const top_k = event.top_k || 5;
  const min_score = event.min_score ?? 0.8;

  if (!ids.length || !vectors.length) {
    // In echter Implementierung: lade Embeddings aus S3 anhand embeddingsS3Key
    console.log("Stub mode: expecting inline ids+vectors in event for now.");
    return { ok:false, error: "No inline ids+vectors provided in stub." };
  }

  if (method === "faiss"){
    // Placeholder: In Produktion via Lambda-Container mit FAISS-Bindings oder ECS Task.
    return { ok:false, error: "FAISS mode not implemented in stub. Use method=cosine-numpy or deploy FAISS container." };
  }

  // cosine-numpy equivalent in plain JS
  const normed = normalize(vectors);
  const linked = cosineTopK(normed, ids, top_k, min_score);
  // TODO: persist to DynamoDB kb_items.similar_ids + scores
  return { ok: true, method: "cosine-numpy", top_k, min_score, results: linked };
};
