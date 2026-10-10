<!--
この文書は `shikumi-devdoc` によって生成された canonical document です。
Canonical source は `devdocs/canonical_sources/specification/__init__.py` です。
直接編集しないでください。

公開文書作成方針

- `devdocs/canonical_documents/` にある日本語 canonical document を公開工程の入力とする。
- 翻訳では意味、構造、情報量を維持し、内容を勝手に追加・削除・要約しない。
- canonical document に `shikumi-devdoc:translation-metadata` が含まれる場合は、その `preserve_spelling` 指定の用語の表記を変更しない。
- コード、Python 識別子、コマンド、ファイルパス、URL は、翻訳上の必要がない限り変更しない。
- このコメントブロックは published document には含めない。
- published document は canonical document から派生する公開成果物として扱い、内容の変更が必要な場合は canonical source または realization context へ戻して canonical document を再生成する。
-->

# gpframe Specification

| Document | Summary |
| --- | --- |
| [Session](session.md) | セッションの開閉、フレームの起動、終了時の判定、サブセッションに関する規則。 |
| [Frame](frame.md) | フレームの状態、戻り値と例外の受け取り、失敗の承認に関する規則。 |
| [Stop](stop.md) | 停止の要求、停止の伝わり方、停止コールバックに関する規則。 |
| [Waiting](waiting.md) | すべてのフレームの終了を待つ方法と、最初の失敗を待つ方法に関する規則。 |
| [Shared](shared.md) | 型の固定された共有セル Shared の生成、読み書き、アトミックな更新に関する規則。 |
| [Channel](channel.md) | フレーム間で値を順に受け渡し、送受信の待ちが停止の要求で解ける Channel に関する規則。 |
