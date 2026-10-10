<!--
この文書は `shikumi-devdoc` によって生成された canonical document です。
Canonical source は `devdocs/canonical_sources/specification_aio/__init__.py` です。
直接編集しないでください。

公開文書作成方針

- `devdocs/canonical_documents/` にある日本語 canonical document を公開工程の入力とする。
- 翻訳では意味、構造、情報量を維持し、内容を勝手に追加・削除・要約しない。
- canonical document に `shikumi-devdoc:translation-metadata` が含まれる場合は、その `preserve_spelling` 指定の用語の表記を変更しない。
- コード、Python 識別子、コマンド、ファイルパス、URL は、翻訳上の必要がない限り変更しない。
- このコメントブロックは published document には含めない。
- published document は canonical document から派生する公開成果物として扱い、内容の変更が必要な場合は canonical source または realization context へ戻して canonical document を再生成する。
-->

# gpframe.aio Specification

| Document | Summary |
| --- | --- |
| [Constraints and limits](limits.md) | 非同期版が守れないものを先に定める。利用者が守るべき制約と、gpframe.aio が原理的に保証できない限界。 |
| [Async frame](frame.md) | 非同期のフレームの状態(succeeded / stopped / broken)、結果の受け取り、失敗の承認に関する規則。 |
| [Async session](session.md) | 非同期のセッションの開閉、同期版との型の分離、フレームの起動、終了時の判定、サブセッションに関する規則。 |
| [Async stop](stop.md) | 非同期版の停止の要求とキャンセルの配送、停止の伝わり方、停止コールバックに関する規則。 |
| [Async waiting](waiting.md) | 非同期版で、すべてのフレームの終了と最初の失敗を、ループを止めずに待つ方法に関する規則。 |
| [Health monitoring](health.md) | ループが応答しなくなったことを、ループの外から検出して報告するヘルスチェックに関する規則。セッションの約束の外側にある観測の道具。 |
