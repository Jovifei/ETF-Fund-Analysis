import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ChanEvidenceCard from '../src/components/ChanEvidenceCard.vue'
import fixture from './fixtures/chan_chart_projection.json'
import revision from './fixtures/chan_revision_evidence.json'
import unchangedProjection from './fixtures/chan_unchanged_projection.json'
import type { ChanObservation, ChanRevisionEvidence, ChanTransition } from '../src/lib/types'

const observation = (): ChanObservation & { revision_evidence: ChanRevisionEvidence & { transitions: ChanTransition[] } } => ({ ...structuredClone(fixture.chart.chan_observation) as ChanObservation, revision_evidence: structuredClone(revision) })

describe('saved Chan revision evidence', () => {
  it('uses the verified unchanged status even when observation-bound revision IDs differ', () => {
    const transition = unchangedProjection.revision_evidence.transitions[0]
    expect(transition.revision_id).not.toBe(transition.prior_revision_id)
    const wrapper = mount(ChanEvidenceCard, { props: { observation: unchangedProjection as ChanObservation } })
    expect(wrapper.get('[data-testid="chan-transition"]').text()).toContain('与上次观察一致')
    expect(wrapper.text()).toContain(transition.revision_id)
    expect(wrapper.text()).toContain(transition.prior_revision_id)
  })
  it('starts collapsed and exposes five rows before explicit expansion', async () => {
    const original = observation(), before = structuredClone(original)
    const wrapper = mount(ChanEvidenceCard, { props: { observation: original } })
    expect(wrapper.get('details').attributes('open')).toBeUndefined()
    expect(wrapper.get('summary').text()).toContain('查看已保存缠论证据')
    expect(wrapper.findAll('[data-testid="chan-transition"]')).toHaveLength(5)
    expect(wrapper.text()).toContain('本次新增观察')
    expect(wrapper.text()).toContain('本次观察有变化')
    expect(wrapper.text()).toContain('与上次观察一致')
    expect(wrapper.text()).toContain('本次未观察到')
    expect(wrapper.text()).toContain('再次观察到')
    expect(wrapper.text()).toContain('不表示结构失效')
    expect(wrapper.text()).toContain('引擎确认未知')
    expect(wrapper.text()).toContain('不代表历史当时可见')
    expect(wrapper.text()).toContain('2026-09-08 07:00:00 UTC')
    expect(wrapper.text()).toContain('revision-absent')
    await wrapper.get('[data-testid="chan-evidence-more"]').trigger('click')
    expect(wrapper.findAll('[data-testid="chan-transition"]')).toHaveLength(6)
    expect(wrapper.text()).toContain('变化状态未知')
    expect(original).toEqual(before)
  })

  it.each(['OBSERVED_NEW', 'OBSERVED_CHANGED', 'OBSERVED_UNCHANGED', 'OBSERVED_ABSENT'])('does not assert %s with missing revision identities', status => {
    const value = observation()
    value.revision_evidence.transitions = [{ structure_key: 'known', status, revision_id: null, prior_revision_id: null, reappearance: true }]
    const wrapper = mount(ChanEvidenceCard, { props: { observation: value } })
    expect(wrapper.get('[data-testid="chan-transition"]').text()).toContain('变化状态未知')
    expect(wrapper.get('[data-testid="chan-transition"]').text()).toContain('未知')
    expect(wrapper.get('[data-testid="chan-transition"]').text()).not.toContain('再次观察到')
  })

  it('keeps old responses unknown and an empty verified list explicit', async () => {
    const wrapper = mount(ChanEvidenceCard, { props: { observation: fixture.chart.chan_observation as ChanObservation } })
    expect(wrapper.text()).toContain('当前响应未提供修订变化记录')
    expect(wrapper.text()).not.toContain('没有修订变化条目')
    const value = observation(); value.revision_evidence.transitions = []
    await wrapper.setProps({ observation: value })
    expect(wrapper.text()).toContain('本次观测没有修订变化条目')
  })

  it.each([
    { available: false }, { drawable: false }, { source: 'simplified' },
    { available: undefined }, { drawable: undefined },
  ])('hides the card for unverified or non-drawable observations %j', override => {
    const wrapper = mount(ChanEvidenceCard, { props: { observation: { ...observation(), ...override } } })
    expect(wrapper.find('details').exists()).toBe(false)
  })

  it('does not interpret unknown status or truthy reappearance as confirmation', () => {
    const value = observation() as any
    value.revision_evidence.transitions = [
      { structure_key: 'key', status: '<img src=x onerror=alert(1)>', revision_id: 'id', reappearance: true },
      { structure_key: 'key2', status: 'OBSERVED_NEW', revision_id: 'id2', prior_revision_id: null, reappearance: 'true' },
    ]
    const wrapper = mount(ChanEvidenceCard, { props: { observation: value } })
    expect(wrapper.text()).toContain('变化状态未知')
    expect(wrapper.text()).not.toContain('本次新增观察')
    expect(wrapper.text()).not.toContain('再次观察到')
    expect(wrapper.find('img').exists()).toBe(false)
  })

  it.each([
    ['OBSERVED_NEW', 'current', 'prior', false],
    ['OBSERVED_ABSENT', 'current', 'prior', false],
    ['OBSERVED_ABSENT', null, 'prior', true],
  ])('keeps contradictory revision tuple %s/%s/%s/%s unknown', (status, current, prior, reappearance) => {
    const value = observation()
    value.revision_evidence.transitions = [{ structure_key: 'key', status: status as string, revision_id: current as string | null, prior_revision_id: prior as string | null, reappearance: reappearance as boolean }]
    const wrapper = mount(ChanEvidenceCard, { props: { observation: value } })
    expect(wrapper.get('[data-testid="chan-transition"]').text()).toContain('变化状态未知')
  })

  it.each(['not-a-time', '2026-02-30 15:00:00', '2026-09-08 25:00:00', null])('keeps invalid cutoff %j unknown', value => {
    const data = observation(); data.revision_evidence.cutoff_at = value
    const wrapper = mount(ChanEvidenceCard, { props: { observation: data } })
    const terms = wrapper.findAll('.evidence-metadata dt')
    expect(terms.find(term => term.text() === '来源截止')!.element.nextElementSibling!.textContent).toBe('未知')
  })
})
