import webview from '@ohos.web.webview';

@Entry
@Component
struct Index {
  private controller: webview.WebviewController = new webview.WebviewController();
  @State private loadingText: string = '正在加载识境...';

  onBackPress(): boolean {
    if (this.controller.accessBackward()) {
      this.controller.backward();
      return true;
    }
    return false;
  }

  build() {
    Stack() {
      Web({
        src: $rawfile('web/index.html'),
        controller: this.controller
      })
        .javaScriptAccess(true)
        .domStorageAccess(true)
        .width('100%')
        .height('100%')
        .onPageBegin(() => {
          this.loadingText = '正在加载识境...';
        })
        .onPageEnd(() => {
          this.loadingText = '';
        })
        .onErrorReceive(() => {
          this.loadingText = '页面加载失败，请检查网络或后端服务';
        })

      if (this.loadingText !== '') {
        Column({ space: 14 }) {
          Text('识境')
            .fontSize(28)
            .fontWeight(FontWeight.Bold)
            .fontColor(Color.White)
          Text(this.loadingText)
            .fontSize(14)
            .fontColor('#CFE8DC')
        }
        .justifyContent(FlexAlign.Center)
        .alignItems(HorizontalAlign.Center)
        .width('100%')
        .height('100%')
        .backgroundColor('#06130F')
      }
    }
    .width('100%')
    .height('100%')
    .backgroundColor('#06130F')
  }
}
