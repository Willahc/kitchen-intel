import { useEffect, useMemo, useState } from 'react'
import {
  api,
  type Evidence,
  type HumanAnnotationPayload,
  type Opportunity,
  type ReviewDetail,
  type ReviewSummary,
  type Stats,
} from './api'

const VALID_CATEGORIES = [
  'COZINHA',
  'REFEITORIO',
  'INOX',
  'COCCAO',
  'REFRIGERACAO',
  'EXAUSTAO',
  'LAVAGEM',
  'INFRAESTRUTURA',
  'ALIMENTACAO_COLETIVA',
]

const money = (value: number | null) =>
  value == null
    ? '—'
    : new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL', maximumFractionDigits: 0 }).format(value)
const label = (value: string) => value.replaceAll('_', ' ')

function BarChart({ title, data }: { title: string; data: Record<string, number> }) {
  const max = Math.max(...Object.values(data), 1)
  return (
    <section className="chart">
      <h3>{title}</h3>
      {Object.keys(data).length ? (
        Object.entries(data).map(([key, value]) => (
          <div className="bar-row" key={key}>
            <span>{label(key)}</span>
            <div className="bar-track">
              <i style={{ width: `${(value / max) * 100}%` }} />
            </div>
            <b>{value}</b>
          </div>
        ))
      ) : (
        <p className="muted">Sem dados para este recorte.</p>
      )}
    </section>
  )
}

function Kpi({ label: l, value }: { label: string; value: string | number }) {
  return (
    <article className="kpi">
      <span>{l}</span>
      <strong>{value}</strong>
    </article>
  )
}

function Info({ label: l, value }: { label: string; value: string | null }) {
  return (
    <div>
      <span>{l}</span>
      <b>{value || '—'}</b>
    </div>
  )
}

export default function App() {
  const [activeTab, setActiveTab] = useState<'opportunities' | 'review'>('opportunities')

  // Dashboard state
  const [stats, setStats] = useState<Stats | null>(null)
  const [items, setItems] = useState<Opportunity[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [filters, setFilters] = useState({ q: '', uf: '', category: '', relevance: '', temporal_status: '', min_score: '' })
  const [selected, setSelected] = useState<Opportunity | null>(null)
  const [evidence, setEvidence] = useState<Evidence | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  // Review state
  const [reviewCorpus, setReviewCorpus] = useState<'dev' | 'test'>('dev')
  const [reviewSummary, setReviewSummary] = useState<ReviewSummary | null>(null)
  const [reviewIndex, setReviewIndex] = useState(0)
  const [reviewDetail, setReviewDetail] = useState<ReviewDetail | null>(null)
  const [reviewLoading, setReviewLoading] = useState(false)
  const [blindMode, setBlindMode] = useState(true)
  const [revealBlind, setRevealBlind] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saveFeedback, setSaveFeedback] = useState<{ type: 'success' | 'error'; message: string } | null>(null)

  // Review form state
  const [formRelevant, setFormRelevant] = useState<boolean | null>(null)
  const [formRelevance, setFormRelevance] = useState<string>('')
  const [formCategories, setFormCategories] = useState<string[]>([])
  const [formConfidence, setFormConfidence] = useState<number>(5)
  const [formNotes, setFormNotes] = useState<string>('')
  const [autoAdvance, setAutoAdvance] = useState(true)

  // Load dashboard
  const loadDashboard = async () => {
    setLoading(true)
    setError('')
    try {
      const params = new URLSearchParams({ page: String(page), page_size: '10' })
      Object.entries(filters).forEach(([k, v]) => v && params.set(k, v))
      const [s, list] = await Promise.all([api.stats(), api.opportunities(params)])
      setStats(s)
      setItems(list.items)
      setTotal(list.total)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Falha ao consultar a API')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (activeTab === 'opportunities') {
      loadDashboard()
    }
  }, [activeTab, page, filters.q, filters.uf, filters.category, filters.relevance, filters.temporal_status, filters.min_score])

  const openOpportunity = async (item: Opportunity) => {
    setSelected(item)
    setEvidence(null)
    try {
      const [detail, why] = await Promise.all([api.detail(item.opportunity_id), api.evidence(item.opportunity_id)])
      setSelected(detail)
      setEvidence(why)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Falha ao abrir detalhe')
    }
  }

  // Load review
  const loadReview = async (targetIndex?: number, corpus: 'dev' | 'test' = reviewCorpus) => {
    setReviewLoading(true)
    setError('')
    try {
      const summaryFn = corpus === 'dev' ? api.devReviewSummary : api.reviewSummary
      const summary = await summaryFn()
      setReviewSummary(summary)
      const idx = targetIndex !== undefined ? targetIndex : reviewIndex
      if (summary.items.length > 0 && idx < summary.items.length) {
        await loadItemDetail(summary.items[idx].review_id, corpus)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Falha ao carregar corpus de revisão')
    } finally {
      setReviewLoading(false)
    }
  }

  const loadItemDetail = async (reviewId: string, corpus: 'dev' | 'test' = reviewCorpus) => {
    setRevealBlind(false)
    setSaveFeedback(null)
    try {
      const detailFn = corpus === 'dev' ? api.devReviewDetail : api.reviewDetail
      const detail = await detailFn(reviewId)
      setReviewDetail(detail)
      if (detail.human.is_reviewed) {
        setFormRelevant(detail.human.human_relevant)
        setFormRelevance(detail.human.human_relevance || '')
        setFormCategories(detail.human.human_categories || [])
        setFormConfidence(detail.human.human_confidence ?? 5)
        setFormNotes(detail.human.human_notes || '')
      } else {
        setFormRelevant(null)
        setFormRelevance('')
        setFormCategories([])
        setFormConfidence(5)
        setFormNotes('')
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Falha ao obter detalhe do registro de revisão')
    }
  }

  const handleSwitchCorpus = async (corpus: 'dev' | 'test') => {
    setReviewCorpus(corpus)
    setReviewIndex(0)
    await loadReview(0, corpus)
  }

  useEffect(() => {
    if (activeTab === 'review') {
      loadReview(0, reviewCorpus)
    }
  }, [activeTab])

  const handleSelectRecord = async (index: number) => {
    if (!reviewSummary || index < 0 || index >= reviewSummary.items.length) return
    setReviewIndex(index)
    await loadItemDetail(reviewSummary.items[index].review_id, reviewCorpus)
  }

  const handleSaveAnnotation = async () => {
    if (!reviewDetail) return
    if (formRelevant === null) {
      setSaveFeedback({ type: 'error', message: 'Indique se o registro é RELEVANTE (SIM ou NÃO).' })
      return
    }
    if (!formRelevance) {
      setSaveFeedback({ type: 'error', message: 'Selecione o grau de relevância humana (ALTA, MEDIA, BAIXA ou IRRELEVANTE).' })
      return
    }
    if (!formRelevant && formRelevance !== 'IRRELEVANTE') {
      setSaveFeedback({ type: 'error', message: 'Quando human_relevant for falso, human_relevance deve ser IRRELEVANTE.' })
      return
    }
    if (formRelevant && formRelevance === 'IRRELEVANTE') {
      setSaveFeedback({ type: 'error', message: 'Quando human_relevant for verdadeiro, human_relevance deve ser ALTA, MEDIA ou BAIXA.' })
      return
    }
    if (!formRelevant && formCategories.length > 0) {
      setSaveFeedback({ type: 'error', message: 'Quando human_relevant for falso, human_categories deve ser vazio.' })
      return
    }

    setSaving(true)
    setSaveFeedback(null)
    try {
      const payload: HumanAnnotationPayload = {
        human_relevant: formRelevant,
        human_relevance: formRelevance,
        human_categories: formRelevant ? formCategories : [],
        human_confidence: formConfidence,
        human_notes: formNotes.trim() ? formNotes.trim() : null,
      }
      const saveFn = reviewCorpus === 'dev' ? api.devReviewSave : api.reviewSave
      const updated = await saveFn(reviewDetail.review_id, payload)
      setReviewDetail(updated)
      setSaveFeedback({ type: 'success', message: `Anotação ${reviewDetail.review_id} salva com sucesso!` })

      // Reload summary to reflect updated counters
      const summaryFn = reviewCorpus === 'dev' ? api.devReviewSummary : api.reviewSummary
      const updatedSummary = await summaryFn()
      setReviewSummary(updatedSummary)

      if (autoAdvance) {
        const nextPendingIdx = updatedSummary.items.findIndex((item, i) => i > reviewIndex && !item.is_reviewed)
        if (nextPendingIdx !== -1) {
          setReviewIndex(nextPendingIdx)
          await loadItemDetail(updatedSummary.items[nextPendingIdx].review_id, reviewCorpus)
        } else {
          // Check from beginning
          const wrapPendingIdx = updatedSummary.items.findIndex(item => !item.is_reviewed)
          if (wrapPendingIdx !== -1 && wrapPendingIdx !== reviewIndex) {
            setReviewIndex(wrapPendingIdx)
            await loadItemDetail(updatedSummary.items[wrapPendingIdx].review_id, reviewCorpus)
          } else if (reviewIndex < updatedSummary.items.length - 1) {
            setReviewIndex(reviewIndex + 1)
            await loadItemDetail(updatedSummary.items[reviewIndex + 1].review_id, reviewCorpus)
          }
        }
      }
    } catch (e) {
      setSaveFeedback({ type: 'error', message: e instanceof Error ? e.message : 'Falha ao salvar anotação' })
    } finally {
      setSaving(false)
    }
  }

  const toggleCategory = (cat: string) => {
    if (formCategories.includes(cat)) {
      setFormCategories(formCategories.filter(c => c !== cat))
    } else {
      setFormCategories([...formCategories, cat])
    }
  }

  const relevanceData: Record<string, number> = stats
    ? { ALTA: stats.high, MEDIA: stats.medium, BAIXA: stats.low, IRRELEVANTE: stats.irrelevant }
    : {}
  const temporalData: Record<string, number> = stats
    ? { ATIVA: stats.active, FUTURA: stats.future, ENCERRADA: stats.closed, INDETERMINADA: stats.indeterminate }
    : {}
  const ufs = useMemo(() => [...new Set(items.map(x => x.uf).filter(Boolean))].sort(), [items])

  return (
    <main>
      <header>
        <div>
          <p className="eyebrow">OPPORTUNITY INTELLIGENCE · GATE 4.6</p>
          <h1>KITCHEN INTEL</h1>
        </div>
        <span className="read-only">Ambiente de Inteligência & Ground Truth</span>
      </header>

      {/* Tabs */}
      <nav className="nav-tabs">
        <button
          className={`nav-tab ${activeTab === 'opportunities' ? 'active' : ''}`}
          onClick={() => setActiveTab('opportunities')}
        >
          Radar de Oportunidades (Gold)
        </button>
        <button
          className={`nav-tab ${activeTab === 'review' ? 'active' : ''}`}
          onClick={() => setActiveTab('review')}
        >
          Revisão Humana & Ground Truth (Corpus v0.1.0)
        </button>
      </nav>

      {error && <div className="error">{error}</div>}

      {/* VIEW: OPPORTUNITIES */}
      {activeTab === 'opportunities' && (
        <>
          <section className="intro">
            <div>
              <h2>Radar de oportunidades institucionais</h2>
              <p>Consulta explicável de contratações públicas. Cada resultado mantém regras, evidências e lineage.</p>
            </div>
            <button onClick={loadDashboard}>Atualizar dados</button>
          </section>

          {stats && (
            <>
              <section className="kpis">
                <Kpi label="Total analisado" value={stats.total_gold} />
                <Kpi label="Oportunidades relevantes" value={stats.relevant} />
                <Kpi label="Alta relevância" value={stats.high} />
                <Kpi label="Oportunidades ativas" value={stats.active} />
                <Kpi label="Ticket estimado" value={money(stats.estimated_ticket_total)} />
                <Kpi label="Score médio" value={String(stats.average_opportunity_score ?? '—')} />
                <Kpi label="Confidence média" value={String(stats.average_confidence_score ?? '—')} />
              </section>
              <section className="charts">
                <BarChart title="Por relevância" data={relevanceData} />
                <BarChart title="Por status temporal" data={temporalData} />
                <BarChart title="Por categoria" data={stats.categories} />
              </section>
            </>
          )}

          <section className="work">
            <div className="section-title">
              <div>
                <p className="eyebrow">OPORTUNIDADES</p>
                <h2>Explorar resultados</h2>
              </div>
              <span>{total} registros</span>
            </div>
            <div className="filters">
              <input
                aria-label="Buscar"
                placeholder="Buscar objeto, órgão ou unidade"
                value={filters.q}
                onChange={e => {
                  setPage(1)
                  setFilters({ ...filters, q: e.target.value })
                }}
              />
              <select
                aria-label="UF"
                value={filters.uf}
                onChange={e => {
                  setPage(1)
                  setFilters({ ...filters, uf: e.target.value })
                }}
              >
                <option value="">Todas as UFs</option>
                {ufs.map(uf => (
                  <option key={uf!} value={uf!}>
                    {uf}
                  </option>
                ))}
              </select>
              <select
                aria-label="Categoria"
                value={filters.category}
                onChange={e => {
                  setPage(1)
                  setFilters({ ...filters, category: e.target.value })
                }}
              >
                <option value="">Todas as categorias</option>
                {Object.keys(stats?.categories || {})
                  .sort()
                  .map(cat => (
                    <option key={cat}>{cat}</option>
                  ))}
              </select>
              <select
                aria-label="Relevância"
                value={filters.relevance}
                onChange={e => {
                  setPage(1)
                  setFilters({ ...filters, relevance: e.target.value })
                }}
              >
                <option value="">Toda relevância</option>
                {['ALTA', 'MEDIA', 'BAIXA', 'IRRELEVANTE'].map(x => (
                  <option key={x}>{x}</option>
                ))}
              </select>
              <select
                aria-label="Status"
                value={filters.temporal_status}
                onChange={e => {
                  setPage(1)
                  setFilters({ ...filters, temporal_status: e.target.value })
                }}
              >
                <option value="">Todo status</option>
                {['ATIVA', 'FUTURA', 'ENCERRADA', 'INDETERMINADA'].map(x => (
                  <option key={x}>{x}</option>
                ))}
              </select>
              <input
                aria-label="Score mínimo"
                type="number"
                min="0"
                max="100"
                placeholder="Score mínimo"
                value={filters.min_score}
                onChange={e => {
                  setPage(1)
                  setFilters({ ...filters, min_score: e.target.value })
                }}
              />
            </div>

            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Organização</th>
                    <th>Objeto</th>
                    <th>Local</th>
                    <th>Categorias</th>
                    <th>Relevância</th>
                    <th>Status</th>
                    <th>Valor</th>
                    <th>Score</th>
                    <th>Confidence</th>
                  </tr>
                </thead>
                <tbody>
                  {loading ? (
                    <tr>
                      <td colSpan={9}>Carregando…</td>
                    </tr>
                  ) : (
                    items.map(item => (
                      <tr key={item.opportunity_id} onClick={() => openOpportunity(item)}>
                        <td>
                          <b>{item.orgao_nome || '—'}</b>
                          <small>{item.unidade_nome || 'Sem unidade'}</small>
                        </td>
                        <td className="object">{item.objeto_original || '—'}</td>
                        <td>
                          {item.municipio || '—'}/{item.uf || '—'}
                        </td>
                        <td>{item.categories.length ? item.categories.map(x => <em key={x}>{label(x)}</em>) : '—'}</td>
                        <td>
                          <mark className={`rel ${item.relevance}`}>{item.relevance}</mark>
                        </td>
                        <td>{item.temporal_status}</td>
                        <td>{money(item.valor_total_estimado)}</td>
                        <td>
                          <b>{item.opportunity_score}</b>
                        </td>
                        <td>{item.confidence_score}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
            <div className="pager">
              <button disabled={page === 1} onClick={() => setPage(page - 1)}>
                Anterior
              </button>
              <span>Página {page}</span>
              <button disabled={items.length < 10} onClick={() => setPage(page + 1)}>
                Próxima
              </button>
            </div>
          </section>

          {selected && (
            <aside className="drawer">
              <div className="drawer-head">
                <div>
                  <p className="eyebrow">DETALHE EXPLICÁVEL</p>
                  <h2>{selected.orgao_nome || 'Oportunidade'}</h2>
                </div>
                <button onClick={() => setSelected(null)}>Fechar</button>
              </div>
              <p className="detail-object">{selected.objeto_original}</p>
              <div className="detail-grid">
                <Info label="CNPJ" value={selected.orgao_cnpj} />
                <Info label="Local" value={`${selected.municipio || '—'} / ${selected.uf || '—'}`} />
                <Info label="Modalidade" value={selected.source} />
                <Info label="Valor" value={money(selected.valor_total_estimado)} />
                <Info label="Publicação" value={selected.data_publicacao} />
                <Info label="Status" value={selected.temporal_status} />
              </div>
              <h3>Por que esta oportunidade foi classificada assim?</h3>
              {evidence ? (
                <>
                  <div className="reasons">
                    {evidence.reason_codes.map(code => (
                      <span key={code}>{label(code)}</span>
                    ))}
                  </div>
                  <h4>Termos encontrados</h4>
                  <p>
                    {evidence.matched_terms.length
                      ? evidence.matched_terms.map(x => `${x.term} → ${x.category}`).join(' · ')
                      : 'Nenhum termo de domínio foi encontrado.'}
                  </p>
                  <h4>Breakdown do score</h4>
                  {Object.entries(evidence.score_breakdown).map(([key, value]) => (
                    <div className="breakdown" key={key}>
                      <b>
                        {label(key)}: {value.points ?? 'N/D'} {value.maximum ? `/ ${value.maximum}` : ''}
                      </b>
                      <span>{value.evidence.join(' · ')}</span>
                    </div>
                  ))}
                  <h4>Lineage</h4>
                  <code>{JSON.stringify(evidence.lineage, null, 2)}</code>
                </>
              ) : (
                <p>Carregando explicabilidade…</p>
              )}
              <p className="muted">Link de origem não disponível no registro.</p>
            </aside>
          )}
        </>
      )}

      {/* VIEW: REVIEW & GROUND TRUTH */}
      {activeTab === 'review' && (
        <section className="review-section">
          {/* Header Card */}
          <div className="review-header-card">
            <div className="review-header-top">
              <div>
                <p className="eyebrow" style={{ color: '#9ec2bc' }}>
                  CURADORIA HUMANA · REVISOR WILLIAM · {reviewCorpus === 'dev' ? 'GATE 5D.1 (BLIND REVIEW)' : 'GATE 4.6 (FROZEN)'}
                </p>
                <h2>
                  {reviewCorpus === 'dev'
                    ? 'Development Set v0.1.0 (120 Casos de Calibração)'
                    : 'Test Set / Avaliação Final v0.1.0 (76 Casos Congelados)'}
                </h2>
                <p style={{ margin: '.3rem 0 0', color: '#c7e2dc', fontSize: '.9rem' }}>
                  {reviewCorpus === 'dev'
                    ? 'O corpus é estritamente imutável. As anotações são gravadas exclusivamente em reports/development_annotations_v0.1.0.csv.'
                    : 'O corpus é estritamente imutável. As anotações foram gravadas em reports/human_annotations_v0.1.0.csv.'}
                </p>
                <div style={{ display: 'flex', gap: '.6rem', marginTop: '.8rem' }}>
                  <button
                    type="button"
                    onClick={() => handleSwitchCorpus('dev')}
                    style={{
                      background: reviewCorpus === 'dev' ? '#00e5a3' : '#142d35',
                      color: reviewCorpus === 'dev' ? '#00251a' : '#c7e2dc',
                      fontWeight: 700,
                      padding: '.4rem .8rem',
                      borderRadius: '4px',
                      cursor: 'pointer',
                      border: 'none',
                    }}
                  >
                    ★ Development Set (120 registros · Gate 5D.1)
                  </button>
                  <button
                    type="button"
                    onClick={() => handleSwitchCorpus('test')}
                    style={{
                      background: reviewCorpus === 'test' ? '#00e5a3' : '#142d35',
                      color: reviewCorpus === 'test' ? '#00251a' : '#c7e2dc',
                      fontWeight: 700,
                      padding: '.4rem .8rem',
                      borderRadius: '4px',
                      cursor: 'pointer',
                      border: 'none',
                    }}
                  >
                    Test Set / Avaliação (76 registros · Congelado)
                  </button>
                </div>
              </div>
              <div style={{ display: 'flex', gap: '.8rem', alignItems: 'center' }}>
                <a
                  href={reviewCorpus === 'dev' ? api.devReviewExportUrl() : api.reviewExportUrl()}
                  download={reviewCorpus === 'dev' ? 'development_annotations_v0.1.0.csv' : 'human_annotations_v0.1.0.csv'}
                  className="btn-export"
                >
                  Exportar Anotações (CSV)
                </a>
                <button onClick={() => loadReview(reviewIndex, reviewCorpus)}>Atualizar</button>
              </div>
            </div>

            {reviewSummary && (
              <div className="review-kpi-bar">
                <div className="review-kpi-pill">
                  <span>Total de Registros</span>
                  <strong>{reviewSummary.total}</strong>
                </div>
                <div className="review-kpi-pill">
                  <span>Revisados por William</span>
                  <strong>
                    {reviewSummary.reviewed} ({reviewSummary.progress_percent}%)
                  </strong>
                </div>
                <div className="review-kpi-pill">
                  <span>Pendências Restantes</span>
                  <strong>{reviewSummary.pending}</strong>
                </div>
                <div className="review-kpi-pill">
                  <span>Status da Revisão</span>
                  <strong style={{ color: reviewSummary.pending === 0 ? '#46dba5' : '#ffc459' }}>
                    {reviewSummary.pending === 0 ? 'CONCLUÍDO / PRONTO' : 'AGUARDANDO REVISÃO HUMANA'}
                  </strong>
                </div>
              </div>
            )}
          </div>

          {/* Controls bar */}
          <div className="review-controls">
            {reviewCorpus === 'test' ? (
              <label className="blind-toggle" title="Oculta as predições determinísticas do sistema em registros pendentes para eliminar o viés de ancoragem.">
                <input
                  type="checkbox"
                  checked={blindMode}
                  onChange={e => setBlindMode(e.target.checked)}
                />
                Modo Blind Review (ocultar predição do baseline para eliminar viés de ancoragem)
              </label>
            ) : (
              <div style={{ color: '#46dba5', fontSize: '.85rem', fontWeight: 600 }}>
                🔒 Modo Blind Review Estrito Ativo (Predições de baseline e LLM desabilitadas no DEV)
              </div>
            )}

            {reviewSummary && reviewSummary.items.length > 0 && (
              <div className="review-nav">
                <button
                  disabled={reviewIndex === 0}
                  onClick={() => handleSelectRecord(reviewIndex - 1)}
                >
                  ◀ Anterior
                </button>

                <select
                  className="review-select"
                  value={reviewIndex}
                  onChange={e => handleSelectRecord(Number(e.target.value))}
                >
                  {reviewSummary.items.map((item, idx) => (
                    <option key={item.review_id} value={idx}>
                      #{idx + 1} {item.is_reviewed ? '✓' : '○'} {item.review_id} — {item.orgao_nome ? item.orgao_nome.slice(0, 32) : 'Sem órgão'}
                    </option>
                  ))}
                </select>

                <button
                  disabled={reviewIndex >= reviewSummary.items.length - 1}
                  onClick={() => handleSelectRecord(reviewIndex + 1)}
                >
                  Próximo ▶
                </button>

                <button
                  onClick={() => {
                    const nextPending = reviewSummary.items.findIndex(x => !x.is_reviewed)
                    if (nextPending !== -1) handleSelectRecord(nextPending)
                  }}
                  style={{ background: '#142d35', color: '#fff' }}
                >
                  Ir para próximo pendente
                </button>
              </div>
            )}
          </div>

          {/* Review Workspace */}
          {reviewLoading && !reviewDetail ? (
            <p>Carregando corpus de avaliação…</p>
          ) : reviewDetail ? (
            <div className="review-grid">
              {/* Left Column: Official Procurement Information & Baseline Panel */}
              <div className="review-card">
                <h3>
                  <span>Informações Oficiais do Processo</span>
                  <span className={`badge-status ${reviewDetail.human.is_reviewed ? 'reviewed' : 'pending'}`}>
                    {reviewDetail.human.is_reviewed
                      ? `REVISADO (${reviewDetail.human.reviewed_at?.slice(0, 10)})`
                      : 'PENDENTE DE AVALIAÇÃO'}
                  </span>
                </h3>

                <p className="eyebrow" style={{ marginTop: '1rem' }}>
                  OBJETO DA CONTRATAÇÃO (TEXTO OFICIAL DO EDITAL)
                </p>
                <div className="object-box">{reviewDetail.objeto_original}</div>

                <div className="meta-table">
                  <div>
                    <span>Órgão Contratante</span>
                    <b>{reviewDetail.orgao_nome}</b>
                  </div>
                  <div>
                    <span>Unidade Requisitante</span>
                    <b>{reviewDetail.unidade_nome || '—'}</b>
                  </div>
                  <div>
                    <span>Localidade</span>
                    <b>
                      {reviewDetail.municipio} / {reviewDetail.uf}
                    </b>
                  </div>
                  <div>
                    <span>Valor Total Estimado</span>
                    <b>{money(reviewDetail.valor_total_estimado)}</b>
                  </div>
                  <div>
                    <span>Data de Publicação</span>
                    <b>{reviewDetail.data_publicacao}</b>
                  </div>
                  <div>
                    <span>Identificador Oficial</span>
                    <b style={{ fontSize: '.75rem', wordBreak: 'break-all' }}>{reviewDetail.source_record_id}</b>
                  </div>
                </div>

                {/* Baseline Prediction Section */}
                <h4 style={{ margin: '1.8rem 0 .5rem', fontSize: '1rem' }}>
                  {reviewCorpus === 'dev' ? 'Blind Review Estrito (Isenção Total)' : 'Predição do Baseline Determinístico'}
                </h4>

                {reviewCorpus === 'dev' || !reviewDetail.baseline ? (
                  <div className="blind-notice" style={{ background: '#0f242d', border: '1px solid #1f4756' }}>
                    <strong style={{ color: '#46dba5' }}>🔒 Blind Review Ativo</strong>
                    <p style={{ margin: '.4rem 0 0', fontSize: '.85rem', color: '#c7e2dc' }}>
                      Nenhuma pontuação, termo casado ou predição de modelo é exibida neste conjunto para garantir que a decisão seja 100% isenta de viés de ancoragem.
                    </p>
                  </div>
                ) : blindMode && !reviewDetail.human.is_reviewed && !revealBlind ? (
                  <div className="blind-notice">
                    <strong>🔒 Modo Blind Review ativo</strong>
                    <p style={{ margin: '.3rem 0', fontSize: '.85rem' }}>
                      A predição determinística está oculta para que sua decisão não sofra viés de ancoragem (anchoring bias).
                    </p>
                    <button onClick={() => setRevealBlind(true)}>Revelar predição do sistema</button>
                  </div>
                ) : (
                  <div className="baseline-box">
                    <div className="baseline-row">
                      <span>Relevância predita pelo sistema:</span>
                      <b>
                        <mark className={`rel ${reviewDetail.baseline.relevance}`}>
                          {reviewDetail.baseline.relevance}
                        </mark>
                      </b>
                    </div>
                    <div className="baseline-row">
                      <span>Opportunity Score / Confidence:</span>
                      <b>
                        {reviewDetail.baseline.opportunity_score} / {reviewDetail.baseline.confidence_score}
                      </b>
                    </div>
                    <div className="baseline-row">
                      <span>Categorias identificadas:</span>
                      <b>
                        {reviewDetail.baseline.categories.length
                          ? reviewDetail.baseline.categories.join(', ')
                          : 'Nenhuma'}
                      </b>
                    </div>
                    <div className="baseline-row">
                      <span>Termos de domínio casados:</span>
                      <b style={{ maxWidth: '280px', textAlign: 'right' }}>
                        {reviewDetail.baseline.matched_terms || 'Nenhum'}
                      </b>
                    </div>
                    <div className="baseline-row">
                      <span>Termos negativos detectados:</span>
                      <b style={{ maxWidth: '280px', textAlign: 'right' }}>
                        {reviewDetail.baseline.negative_matches || 'Nenhum'}
                      </b>
                    </div>
                  </div>
                )}
              </div>

              {/* Right Column: Human Review Form (William) */}
              <div className="review-card">
                <h3>
                  <span>Anotação Humana (William)</span>
                  <small style={{ color: '#617477', fontWeight: 600 }}>Registro #{reviewIndex + 1} de {reviewSummary?.total}</small>
                </h3>

                <form
                  onSubmit={e => {
                    e.preventDefault()
                    handleSaveAnnotation()
                  }}
                  style={{ marginTop: '1rem' }}
                >
                  {/* Field: human_relevant */}
                  <div className="form-field">
                    <label>1. Esta oportunidade é de fato relevante para Cozinha Industrial?</label>
                    <div className="radio-group">
                      <label className="radio-label">
                        <input
                          type="radio"
                          name="human_relevant"
                          checked={formRelevant === true}
                          onChange={() => {
                            setFormRelevant(true)
                            if (formRelevance === 'IRRELEVANTE' || !formRelevance) {
                              setFormRelevance('MEDIA')
                            }
                          }}
                        />
                        SIM (Relevante)
                      </label>
                      <label className="radio-label">
                        <input
                          type="radio"
                          name="human_relevant"
                          checked={formRelevant === false}
                          onChange={() => {
                            setFormRelevant(false)
                            setFormRelevance('IRRELEVANTE')
                          }}
                        />
                        NÃO (Irrelevante)
                      </label>
                    </div>
                    <div className="field-desc">Classificação binária de negócio para Ground Truth.</div>
                  </div>

                  {/* Field: human_relevance */}
                  <div className="form-field">
                    <label>2. Grau de Relevância</label>
                    <div className="radio-group" style={{ flexWrap: 'wrap' }}>
                      {['ALTA', 'MEDIA', 'BAIXA', 'IRRELEVANTE'].map(rel => (
                        <label className="radio-label" key={rel}>
                          <input
                            type="radio"
                            name="human_relevance"
                            value={rel}
                            checked={formRelevance === rel}
                            onChange={() => {
                              setFormRelevance(rel)
                              if (rel === 'IRRELEVANTE') {
                                setFormRelevant(false)
                                setFormCategories([])
                              } else {
                                setFormRelevant(true)
                              }
                            }}
                          />
                          {rel}
                        </label>
                      ))}
                    </div>
                    <div className="field-desc">
                      ALTA (equipamentos centrais de cozinha), MEDIA (utensílios/refeitório), BAIXA (alimentos/merenda
                      pura sem cozinha), IRRELEVANTE (fora do escopo).
                    </div>
                  </div>

                  {/* Field: human_categories */}
                  <div className="form-field">
                    <label>3. Categorias Aplicáveis {formRelevant === false && <span style={{ color: '#ff8a8a', fontSize: '.8rem' }}>(Desabilitado para IRRELEVANTE)</span>}</label>
                    <div className="category-checkboxes">
                      {VALID_CATEGORIES.map(cat => (
                        <label
                          key={cat}
                          className="cat-label"
                          style={{
                            opacity: formRelevant === false ? 0.4 : 1.0,
                            cursor: formRelevant === false ? 'not-allowed' : 'pointer',
                          }}
                        >
                          <input
                            type="checkbox"
                            disabled={formRelevant === false}
                            checked={formCategories.includes(cat)}
                            onChange={() => toggleCategory(cat)}
                          />
                          {cat}
                        </label>
                      ))}
                    </div>
                    <div className="field-desc">Selecione todas as categorias do domínio que se aplicam ao objeto.</div>
                  </div>

                  {/* Field: human_confidence */}
                  <div className="form-field">
                    <label>4. Confiança da sua Anotação (1 a 5)</label>
                    <div className="confidence-bar">
                      {[1, 2, 3, 4, 5].map(lvl => (
                        <button
                          type="button"
                          key={lvl}
                          className={`conf-btn ${formConfidence === lvl ? 'selected' : ''}`}
                          onClick={() => setFormConfidence(lvl)}
                        >
                          {lvl} {lvl === 1 ? '· Dúvida' : lvl === 5 ? '· Certeza' : ''}
                        </button>
                      ))}
                    </div>
                    <div className="field-desc">
                      1 = Alta incerteza no objeto; 3 = Razoável; 5 = Certeza absoluta após ler o edital.
                    </div>
                  </div>

                  {/* Field: human_notes */}
                  <div className="form-field">
                    <label>5. Observações e Justificativa (Opcional)</label>
                    <textarea
                      className="notes-input"
                      maxLength={1000}
                      value={formNotes}
                      placeholder="Adicione justificativa caso seja caso ambíguo, falso positivo sutil ou particularidade do edital..."
                      onChange={e => setFormNotes(e.target.value)}
                    />
                    <div className="field-desc">{formNotes.length}/1000 caracteres</div>
                  </div>

                  {/* Form Submit and Feedback */}
                  <div className="form-actions">
                    <label style={{ display: 'flex', alignItems: 'center', gap: '.4rem', fontSize: '.85rem' }}>
                      <input
                        type="checkbox"
                        checked={autoAdvance}
                        onChange={e => setAutoAdvance(e.target.checked)}
                      />
                      Avançar para o próximo pendente após salvar
                    </label>

                    <button type="submit" disabled={saving} className="btn-save-review">
                      {saving ? 'Salvando…' : 'Salvar Avaliação de William'}
                    </button>
                  </div>

                  {saveFeedback && (
                    <div className={`save-feedback ${saveFeedback.type}`}>{saveFeedback.message}</div>
                  )}
                </form>
              </div>
            </div>
          ) : (
            <p>Nenhum registro selecionado.</p>
          )}
        </section>
      )}
    </main>
  )
}
