<!--
この文書は `shikumi-devdoc` によって生成された canonical document です。
Canonical source は `devdocs/canonical_sources/changelog/canonical.py` です。
直接編集しないでください。

公開文書作成方針

- `devdocs/canonical_documents/` にある日本語 canonical document を公開工程の入力とする。
- 翻訳では意味、構造、情報量を維持し、内容を勝手に追加・削除・要約しない。
- canonical document に `shikumi-devdoc:translation-metadata` が含まれる場合は、その `preserve_spelling` 指定の用語の表記を変更しない。
- コード、Python 識別子、コマンド、ファイルパス、URL は、翻訳上の必要がない限り変更しない。
- このコメントブロックは published document には含めない。
- published document は canonical document から派生する公開成果物として扱い、内容の変更が必要な場合は canonical source または realization context へ戻して canonical document を再生成する。
-->

# gpframe 変更履歴

`gpframe` の版ごとの変更を記録する。

## V0_1_0

旧実装を破棄し、設計を縮小して一から作り直した最初の版。`0.0.x` 系との後方互換性はない。

旧設計は、スレッドとプロセスの実行形態の統一、4 チャンネルの型付きメッセージ、ライフサイクルハンドラまでを一度に抱えて大きくなりすぎ、実装が追いつかなかった。この版では、旧設計の芯だった「失敗を握りつぶさない」「止まらなかった処理を報告する」という二つの考え方と、メッセージで練り上げた整合性のルール(型の固定、生成時の初期化、アトミックな更新)だけを残し、それ以外は標準ライブラリと Python の構文に返した。

version: 0.1.0

Added:

- `gpframe.session()` で開くセッションと、`spawn()` で起動するフレームを追加した。フレームはルーティンの戻り値を持ち、`result()` で受け取れる。
- 失敗したフレームを `ignore()` / `escalate()` で承認する仕組みを追加した。ルートのセッションの終了時に、`escalate()` された失敗は `SessionFailed`(`ExceptionGroup`)として送出し、マークのない失敗は `FrameWarning` で警告する。`strict=True` ではマークのない失敗も送出する。
- 協調的な停止(`stop()`、`Context.stopping`、`Context.wait_stop()`)と、セッションの終了時に `timeout` 秒で待機を打ち切り、止まらなかったフレームを報告する仕組みを追加した。
- `Context.session()` によるサブセッションを追加した。サブセッションは不完全だった場合に報告を親フレームに付け、最終的な判断はルートのセッションが行う。
- ブロックする処理を止めるための停止コールバック `Context.on_stop()` を追加した。コールバックは別のスレッドで一度だけ呼ばれ、例外は `Frame.stop_errors` に記録されてフレームを broken にする。登録は `StopHandle.cancel()` で取り消せる。
- 最初の失敗を待つ `Session.wait_broken()` を追加した。長く動き続ける部品を連結し、どれか一つが失敗したら全体を止める処理を、ポーリングなしで書ける。`idle=True` を指定すると、実行中のフレームがなくても失敗か停止の要求まで待ち続ける。
- 終わり方を問わずにフレームの終わりを待つ `Frame.wait()` と `AsyncFrame.wait()` を追加した。
- セッションは、判定に要らなくなったフレーム(succeeded、stopped、`ignore()` 済み)を手放し、終わったフレームはルーティンと引数への参照を手放す。要求ごとにフレームを起動する長寿命のセッションでも、メモリが溜まらない。
- 型と初期値を生成時に決める共有セル `Shared` を追加した。
- フレーム間で値を順に受け渡す `Channel` を追加した。受け取りは停止の要求で待ちが解けるので、受け取りのループを書くだけで止められるワーカーになる。容量の上限 `maxsize` を付けると、`put(item, ctx)` は空きが出るまで待ち、停止の要求か `close()` で待ちを解く。
- 停止を要求されたセッションの `spawn()` は、ルーティンを呼ばない stopped のフレームを返す(同期版・非同期版とも)。止まる途中で始めようとした仕事を失敗にしない。
- gpframe で書いた開発用ウォッチャー `tools/devwatch.py` と、`gpframe.aio` で書いたチャットサーバーの例 `examples/chat.py`、`Channel` でつないだログ集計のパイプラインの例 `examples/logstats.py` を追加した。
- asyncio のイベントループの上でフレームをタスクとして動かす非同期版 `gpframe.aio` を追加した。同期版とは型を共有しない独立した API で、停止はタスクのキャンセルで行い、停止の要求で終わったフレームは stopped として失敗に数えない。
- ループの停滞をループの外のスレッドから検出して報告するヘルスチェック `gpframe.aio.monitor()` を追加した。
- 守るべき振る舞いを `shikumi-contrace` の契約として `contract/` に追加し、すべての条項をテストに結びつけた。
- README、Project Status、CHANGELOG を `shikumi-devdoc` の正本として `devdocs/` に追加した。
- canonical document を翻訳した英語の公開文書を、リポジトリのルート(README、STATUS、CHANGELOG)と `docs/`(Specification)に追加した。翻訳が canonical document と食い違っていないことを `scripts/published_docs.py` で確かめる。
- すべての検査をまとめた `tools/check.py` と、GitHub Actions の CI(`ci.yml`)とリリース(`release.yml`)を追加した。リリースは CI と同じ検査を通したうえで、PyPI の Trusted Publishing で公開する。
- 振る舞いの規則を Specification として追加した。同期版はセッション、フレーム、停止、待機、`Shared`、`Channel` の 6 文書、非同期版は制約と限界、フレーム、セッション、停止、待機、ヘルスチェックの 6 文書である。契約の各条項から根拠となる規則を指すようにした。

Changed:

- 対象の Python を `>=3.11` に変更した。

Removed:

- `0.0.x` 系の実装と API をすべて削除した。`create_frame()` などのフレームビルダー、ルートとサブのフレーム・セッションの区別、`FrameResult` とマーク用の各メソッドは、セッションとフレームの新しい API に置き換わった。
- 4 チャンネルのメッセージ(`environment` / `request` / `common` / `local`)を削除した。設定はルーティンの引数、停止の指示は `stop()`、値の受け渡しは `Channel`、結果はフレームの戻り値、共有状態は `Shared` で扱う。
- ライフサイクルハンドラ(`on_open` / `on_start` / `on_end` / `on_redo` / `on_exception` / `on_close`)を削除した。ルーティン内の `try` / `finally`、`while`、`except` で書く。
- サブプロセスでの実行と、そのためのプロセス間通信を削除した。
- 旧設計の下書きと仕様の置き場だった `design/` と、旧テストを削除した。
