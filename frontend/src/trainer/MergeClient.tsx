import { useEffect, useState } from 'react'

import { errorText, fetchClients, mergeClient, type Client } from '../api'
import { fullName } from '../format'
import { confirmAction, haptic } from '../telegram'
import { PersonAvatar } from '../ui/Avatar'
import { EmptyState, ErrorText, Row, Section, SkeletonList } from '../ui/kit'
import Screen from '../ui/Screen'

type Props = {
  client: Client
  onBack: () => void
  onMerged: () => void
}

/** Клиент без Telegram сам зашёл по общей ссылке: склеиваем две карточки в одну. */
export default function MergeClient({ client, onBack, onMerged }: Props) {
  const [clients, setClients] = useState<Client[] | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchClients()
      .then((loaded) => setClients(loaded.filter((item) => !item.offline)))
      .catch((err: unknown) => setError(errorText(err)))
  }, [])

  async function merge(into: Client) {
    if (busy) return
    const ok = await confirmAction(
      `${fullName(client)} и ${fullName(into)} — один человек? ` +
        `Записи, блоки и заметки перейдут к ${fullName(into)}.`,
      'Объединить',
    )
    if (!ok) return
    setBusy(true)
    setError(null)
    try {
      await mergeClient(client.id, into.id)
      haptic.success()
      onMerged()
    } catch (err) {
      haptic.error()
      setError(errorText(err))
      setBusy(false)
    }
  }

  return (
    <Screen title="Тот же человек" subtitle={fullName(client)} onBack={onBack}>
      {error && <ErrorText>{error}</ErrorText>}
      {clients === null && !error && <SkeletonList rows={2} />}
      {clients !== null && clients.length === 0 && (
        <EmptyState
          icon="users"
          title="Нет клиентов из Telegram"
          text="Когда клиент перейдёт по вашей ссылке, его можно будет выбрать здесь."
        />
      )}
      {clients !== null && clients.length > 0 && (
        <Section
          title="Выберите клиента из Telegram"
          footer="История из этой карточки перейдёт к выбранному клиенту. Отменить это нельзя."
        >
          {clients.map((item) => (
            <Row
              key={item.id}
              title={fullName(item)}
              subtitle={item.username ? `@${item.username}` : undefined}
              leading={<PersonAvatar person={item} />}
              onClick={() => void merge(item)}
            />
          ))}
        </Section>
      )}
    </Screen>
  )
}
