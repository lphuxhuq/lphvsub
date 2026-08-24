---
name: srt-whiteboard-animation
description: Biến phụ đề SRT thành video animation vẽ tay kiểu whiteboard trên nền giấy be ấm: đọc phụ đề → đưa chiến lược minh họa → sau khi được xác nhận thì sinh line art phong cách thống nhất → đánh dấu phân vùng theo ngữ nghĩa kể chuyện → chỉnh trên trạm xem trước → render MP4. Điều phối theo cơ chế tiết lộ phân vùng bằng mask (annotation.json / sequence / startMs / protectedRegions), nhưng nét vẽ trong mỗi vùng là stream liên tục (khung xương/lưới, ink→color). Kích hoạt khi người dùng cung cấp phụ đề SRT và yêu cầu "làm phụ đề thành video vẽ tay whiteboard / nét vẽ stream", "SRT tạo whiteboard animation", "phân cảnh theo phụ đề để vẽ tay".
---

# SRT Whiteboard Animation (điều phối mask + cách vẽ stream)

Biến phụ đề SRT thành animation whiteboard vẽ tay: **điều phối** dùng cơ chế tiết lộ theo phân vùng mask (lần lượt hiển thị từng vùng theo thứ tự kể chuyện, vùng chưa bắt đầu bị ẩn hoàn toàn, vùng chồng lấp được bảo vệ bằng `protectedRegions`); **cách vẽ** dùng nét stream liên tục — trong mỗi vùng, đầu bút trượt liên tục và để lại nét mực bên trong mask cho phép của vùng đó (mở màn bằng `ink` phác thảo → tiếp tục `color` tô màu), mọi vùng dùng chung một canvas cố định, vùng đã vẽ xong được giữ lại trên canvas. Toàn bộ nội dung giải thích, phân cảnh, cấu hình và chữ trên giao diện hướng tới người dùng phải dùng **tiếng Việt**.

Khác với kiểu nhảy từng khung hay lau hình chữ nhật: nét vẽ của skill này **liên tục và mượt**; khác với stream nguyên hình: skill này vẽ **lần lượt theo phân vùng ngữ nghĩa phụ đề**, kiểm soát được thứ tự xuất hiện và thời điểm của từng phần tử.

## Tham số mặc định

| Mục | Yêu cầu mặc định |
|---|---|
| Nền giấy | Ảnh sinh ra dùng màu giấy cũ be ấm (gợi ý `#F5EBD7`); khi render lấy mẫu màu nền từ ảnh gốc lùi vào từ bốn góc, cấm nền trắng tinh. |
| Cách vẽ | Mỗi vùng một nét stream liên tục: mở màn `ink` (phủ line art) → tiếp `color` (phục hồi màu gốc); tỉ trọng `ink:color = 2:1`. |
| Đường nét | `--ink-path grid` (lưới, mặc định, ổn định) hoặc `skeleton` (bám khung xương, hợp với minh họa line art rõ nét). |
| Kiểu tô màu | `--color-fill contour-wipe` (quét viền, mặc định) hoặc `brush` (quét theo quỹ đạo). |
| Vùng chưa vẽ | Mask cho phép của vùng = hình chữ nhật `region` trừ đi (các vùng sau đó + protectedRegions); vùng chưa bắt đầu bị ẩn hoàn toàn. |
| Nguồn thời lượng | `sceneDurationMs` của mỗi ảnh lấy từ khoảng thời gian phụ đề của cảnh đó (khuyến nghị 25–35 giây/cảnh). |
| Khung chỉnh sửa | Trạm xem trước mặc định hiển thị đầy đủ các khung chỉnh sửa có đánh số; khung chỉnh sửa không thuộc nội dung hình ảnh animation. |

## Quy chuẩn hình ảnh thống nhất (bắt buộc)

Ảnh nguồn của mọi cảnh phải tuân theo cùng một ngôn ngữ thị giác; trước khi sinh ảnh phải ghi đầy đủ các yêu cầu sau vào prompt sinh ảnh, sau khi sinh phải kiểm tra từng mục:

- **Phong cách & bố cục:** minh họa vẽ tay tối giản, phong cách phác thảo thuần khiết, mỹ học doodle tiết chế kiểu Notion. Lấy diễn đạt ý tưởng làm trọng tâm, không chạy theo tính hiện thực; bố cục gọn gàng, nền sạch, nhiều khoảng trống, cảm xúc chung bình thản, rõ ràng; nét vẽ / nhân vật / bảng màu nhất quán trong toàn series.
- **Màu sắc & chất liệu:** nền giấy be `#F5EBD7`, nét phác màu xám đậm; chỉ được dùng đỏ, cam, xanh dương làm điểm nhấn khái niệm. Không dùng màu nhấn khác, bảng màu bão hòa cao hay chất liệu phức tạp.
- **Nhân vật & vật thể:** đối tượng được diễn đạt bằng viền gọn, ít nét và khoảng trống; nhấn mạnh quan hệ / biến đổi / ý tưởng cốt lõi, chứ không phải tỉ lệ thật, chất liệu hay chi tiết.
- **Tuyệt đối cấm:** bất kỳ chữ, từ, mẫu tự, số, font hay nhãn nào trong ảnh nguồn của cảnh; cảm giác hiện thực, chi tiết nhiếp ảnh, hiệu ứng 3D, chất sơn vẽ; cảnh phức tạp, nền dày đặc, trang trí rườm rà và hình ảnh bão hòa cao.
- **Ngoại lệ bàn tay vẽ:** nếu người dùng nói rõ chữ trên thân bút là nhận diện của họ và yêu cầu giữ lại, có thể giữ nhận diện trên thân bút của `drawing-hand.png`; nó không thuộc phạm vi chữ trong ảnh nguồn của cảnh, không cần xóa hay vẽ lại. Khi người dùng chưa nói rõ, vẫn xử lý theo chuẩn ảnh không chữ.

## Cổng xác nhận (bắt buộc)

Trong quy trình mặc định, **sau khi hoàn thành mỗi bước phải dừng lại và chờ người dùng xác nhận rõ ràng** rồi mới được bắt đầu bước tiếp theo. Trước khi được xác nhận, không được sinh ảnh, đánh dấu, bản xem trước, video hay file gộp của bước sau; không được coi "chưa phản hồi", "sự cho phép chung chung trước đây", "người dùng không phản đối" là xác nhận. Khi người dùng yêu cầu sửa bước trước, chỉ làm lại đúng bước đó, và sau khi xong lại chờ xác nhận.

Hành động đi kèm duy nhất: **sau khi file JSON đánh dấu được tạo xong, phải ngay lập tức tự mở trạm xem trước và nạp thư mục chứa JSON đó**; việc này thuộc phần bàn giao của bước 3, không cần chờ xác nhận riêng cho việc "mở trạm xem trước". Nếu File System Access API của trình duyệt yêu cầu thao tác thủ công từ người dùng, dùng giao diện trình duyệt để chọn đúng thư mục đã xác định này; không được vì lý do đó mà xin xác nhận thêm hay đổi sang yêu cầu người dùng tự mở trạm xem trước.

## Quy trình làm việc

1. **Đọc phụ đề, đưa chiến lược (không sinh ảnh).** Dùng `scripts/parse_srt.py` phân tích SRT thành các dòng phụ đề và đề xuất phân cảnh theo 25–35 giây/cảnh. Dựa vào đó đưa ra chiến lược minh họa: mỗi cảnh có số thứ tự, ý chính cần diễn đạt, chủ thể hình ảnh, khoảng phụ đề tương ứng và `sceneDurationMs`. Mỗi cảnh chỉ diễn đạt một ý chính. **Xong thì dừng, chờ người dùng xác nhận chiến lược.**
2. **Sinh line art.** Chỉ khi người dùng đã xác nhận chiến lược, theo "Quy chuẩn hình ảnh thống nhất" sinh lần lượt từng cảnh ảnh line art 16:9 trên nền giấy cũ be ấm `#F5EBD7`, giữa các chủ thể giữ khoảng trống đủ rộng để tiện tách vùng tự động; không được sinh chữ, ảnh phức tạp, đối tượng chồng lấp hay yếu tố trái quy chuẩn. **Xong thì dừng, trình bày line art và chờ người dùng xác nhận.**
3. **Đọc phụ đề trước rồi xem ảnh, sau đó đánh dấu và mở trạm xem trước.** Chỉ khi người dùng đã xác nhận line art, trước tiên đọc phụ đề tương ứng của ảnh đó, rồi thực sự xem ảnh, và lấy kích thước pixel gốc của ảnh; không được chỉ đoán hình ảnh từ phụ đề, cũng không được sắp thứ tự máy móc theo vị trí trên ảnh. Trước hết chắt lọc sự kiện kể chuyện trong phụ đề, rồi ánh xạ chủ thể nhìn thấy trong ảnh sang các sự kiện, sắp thứ tự vẽ theo ngữ nghĩa "dựng cảnh → nhân vật/vật thể chính → xung đột hành động hoặc biến đổi → phản ứng/kết quả". Sau đó tạo `<tên ảnh>.annotation.json`. Ngay khi tạo xong, mở `assets/preview.html` bằng trình duyệt mặc định, và qua chức năng "打开文件夹" (Mở thư mục) của trạm xem trước, nạp toàn bộ `<tên>.png` + `<tên>.annotation.json` trong **thư mục chứa file đánh dấu đó**; không được chỉ đưa đường dẫn file hay yêu cầu người dùng tự thao tác. **Sau khi trạm xem trước đã nạp thư mục thì dừng, chờ người dùng xác nhận đánh dấu và nội dung xem trước.**
4. **Sinh ảnh xem trước phân vùng.** Chỉ khi người dùng đã xác nhận đánh dấu và nội dung xem trước, dùng `render_annotation_preview.py` xuất ảnh kiểm tra số thứ tự/hướng, đối chiếu phân vùng khớp thứ tự kể chuyện, các vùng đều nằm trong canvas, chủ thể chồng lấp được bảo vệ bằng `protectedRegions`. **Xong thì dừng, chờ người dùng xác nhận ảnh xem trước.**
5. **Chỉnh trong trạm xem trước và lưu.** Chỉ khi người dùng đã xác nhận ảnh xem trước, chỉnh trong trạm xem trước đã mở và đã nạp thư mục tương ứng: mặc định (chưa phát) hiển thị ảnh đầy đủ và khung vùng; canvas là **hình chữ nhật đại diện**: kéo bốn cạnh/bốn góc vùng để đổi `region`, cột phải đổi tên/hướng/"开始/结束" (bắt đầu/kết thúc, ms; thời lượng = kết thúc − bắt đầu, chỉ đọc) và **phụ đề**, kéo thả danh sách mô-đun **để đổi thứ tự** (tự sắp lại `sequence`), chọn mô-đun sẽ tự động highlight phụ đề tương ứng; kéo timeline hoặc nhấn phát để xem tiết lộ (vùng chưa bắt đầu không hiển thị); `direction` chỉ tác động lên hình đại diện này. Sửa xong nhấn "保存本场景/全部保存" (Lưu cảnh này/Lưu tất cả) để ghi trở lại `.annotation.json` gốc (bao gồm `subtitle` của mỗi vùng, và căn `sceneDurationMs` bằng thời điểm kết thúc của vùng cuối + 0,5 giây). **Sau khi lưu thì dừng, chờ người dùng xác nhận đánh dấu và thời lượng cuối cùng.**
6. **Render thành phẩm bằng dòng lệnh.** Chỉ khi người dùng đã xác nhận đánh dấu và thời lượng cuối cùng, dùng `render_stream_whiteboard.py` xuất MP4 sạch từng cảnh, kiểm tra ngẫu nhiên ba thời điểm: mở màn, giữa đoạn của bất kỳ mô-đun chồng lấp nào, và kết thúc. **Xong thì dừng, chờ người dùng xác nhận thành phẩm.**
7. **Gộp nhiều cảnh (chỉ áp dụng khi có nhiều cảnh).** Chỉ khi người dùng đã xác nhận tất cả thành phẩm từng cảnh, dùng `merge_scenes.py` gộp theo thứ tự thành một video duy nhất. **Xong thì dừng, chờ người dùng xác nhận video tổng hợp cuối cùng.**

## Quy ước thư mục

Tạo trong project của người dùng:

```text
assets/whiteboard/<tên project>/
  scene-01-<tên>.png
  scene-01-<tên>.annotation.json     # cùng tên với png
  scene-01-<tên>-whiteboard.mp4      # thành phẩm
  scene-01-<tên>-preview.mp4         # đoạn video thật (do trạm xem trước sinh, độ phân giải thấp)
```

Ảnh và cấu hình phải cùng tên: `foo.png` ứng với `foo.annotation.json`. Trạm xem trước dựa vào đó để tự nạp cấu hình.

## Sắp thứ tự ngữ nghĩa và đánh dấu cấp pixel (bắt buộc thực hiện)

1. **Căn cứ đọc:** trước khi đánh dấu phải có đồng thời phụ đề và ảnh gốc đã xem. Thiếu mục nào thì xin mục đó trước, không được sinh đánh dấu.
2. **Căn cứ thứ tự:** `sequence`, `startMs` và `label` phải phản ánh trình tự sự kiện trong phụ đề, chứ không phải chỉ theo trái sang phải, trên xuống dưới hay mức độ nổi bật về thị giác.
3. **Căn cứ tọa độ:** mỗi mô-đun xuất ra `x`, `y`, `width`, `height` là số pixel nguyên trong hệ tọa độ ảnh gốc; gốc tọa độ ở góc trên bên trái, cấm tọa độ phần trăm/tỉ lệ/ước lượng hoặc bỏ qua kích thước. `canvas.width`/`canvas.height` phải bằng đúng kích thước pixel của ảnh gốc.
4. **Trường của mô-đun:** mỗi phần tử gồm `sequence`, `narrativeRole`, `subtitle`, `region`, `reveal`, `handPath`. `narrativeRole` diễn đạt bằng tiếng Việt vai trò kể chuyện của nó trong phụ đề; `subtitle` lưu đoạn phụ đề tương ứng của vùng đó (lấy từ SRT, phục vụ liên kết trạm xem trước và mục đích sử dụng sau này); `sequence` liên tục bắt đầu từ 1.
5. **Kiểm tra:** trước khi sinh bản xem trước, kiểm tra mỗi vùng có nằm trong canvas, có phủ đúng chủ thể nhìn thấy, có khớp sự kiện phụ đề; chủ thể chồng lấp phải được bảo vệ bằng `protectedRegions` rồi mới dựng mô-đun.

## Mô hình thời lượng (dành riêng cho cách vẽ stream)

- **Tổng thời lượng mỗi cảnh:** `sceneDurationMs` lấy từ khoảng thời gian phụ đề của cảnh đó (`scenes[].sceneDurationMs` của `parse_srt.py`).
- **Vẽ tuần tự từng vùng:** cách vẽ stream chỉ có một bút đang chuyển động, các vùng trong cùng một cảnh phải **diễn ra lần lượt về thời gian** (`startMs` không chồng lấp): vùng sau bắt đầu từ `startMs + durationMs` của vùng trước (+ 100–300 ms "thở" tùy chọn). Nếu `startMs` bị chồng lấp, renderer vẫn xử lý theo thứ tự, nhưng về thị giác sẽ không còn là đồng thời.
- **Trong một vùng ink→color:** `durationMs` của mỗi vùng được chia theo `ink:color = 2:1` thành đoạn mở màn và đoạn tô màu. `durationMs` do **thời điểm bắt đầu/kết thúc** của trạm xem trước quyết định (kết thúc − bắt đầu), có thể căn theo thời lượng phụ đề tương ứng của vùng; cũng có thể dùng 150 pixel/giây × khoảng cách vẽ làm ước lượng ban đầu.
- **Kết thúc nhìn ngắm:** sau khi vẽ xong toàn bộ vùng, tự động lấp thêm đến `sceneDurationMs`, và bảo đảm cuối video giữ nguyên ảnh gốc đầy đủ ít nhất 0,5 giây.
- `reveal.direction` dưới cách vẽ stream **không quyết định nét thật** (nét do khung xương/lưới tự sinh), chỉ dùng cho hình chữ nhật đại diện của trạm xem trước; giữ lại để trạm xem trước còn hoạt động được.

## Bất biến mask (tầng điều phối, bắt buộc thực hiện)

- Tại thời điểm `t`, mô-đun chỉ được hiển thị những pixel sau `reveal.startMs ≤ t` và không vượt quá tiến độ đang vẽ; không một nét/nền/ảnh nào của mô-đun chưa bắt đầu được xuất hiện.
- **Mask cho phép** của mỗi vùng = hình chữ nhật `region` trừ đi toàn bộ **`region` của các mô-đun sau**, rồi trừ tiếp `reveal.protectedRegions` của mô-đun này. Nét stream bị giới hạn trong mask cho phép, nên các vùng sau sẽ không lộ nét sớm.
- `protectedRegions` dùng tọa độ pixel nguyên của ảnh gốc, cùng kiểu với `region`, dùng cho các tình huống hình chữ nhật quá lớn, chủ thể chồng lấp hoặc nét nền có nguy cơ lộ.
- Renderer đã hiện thực "giới hạn nét trong mask cho phép → vùng sau và vùng bảo vệ tự nhiên không bị chạm tới"; hình chữ nhật đại diện của trạm xem trước dùng phép trừ `destination-out` tương đương để diễn đạt cùng một điều phối.

## Ví dụ cấu hình

```json
{
  "sceneId": "scene-01",
  "canvas": { "width": 1672, "height": 941 },
  "storyBasis": "Tóm tắt sự kiện của cảnh này theo phụ đề",
  "sceneDurationMs": 9000,
  "elements": [
    {
      "id": "rockery",
      "label": "Cảnh núi đá",
      "sequence": 1,
      "narrativeRole": "Dựng bối cảnh mở đầu cho câu chuyện",
      "subtitle": "Trên núi khỉ, một chú khỉ con ngồi trên đỉnh núi đá, trong tay cầm một quả chuối.",
      "type": "structure",
      "region": { "x": 20, "y": 120, "width": 540, "height": 780 },
      "reveal": { "direction": "top_to_bottom", "startMs": 300, "durationMs": 2600, "maskPaddingPx": 22, "protectedRegions": [] },
      "handPath": { "start": [290, 130], "end": [290, 890], "easing": "easeInOut" }
    }
  ]
}
```

> `direction` / `handPath` chỉ dùng cho hình chữ nhật đại diện của trạm xem trước; nét vẽ thành phẩm do stream tự sinh, không cần tinh chỉnh.

## Dùng script

Mọi script render chạy bằng interpreter trong `.venv` của skill (cách ly dependency).

1. **Chuẩn bị môi trường** (lần đầu hoặc thiếu dependency):
   ```bash
   python scripts/prepare_env.py --check   # dò; khi thành công dòng cuối in ENV_PY=<đường dẫn>, ghi lại để dùng
   python scripts/prepare_env.py           # thiếu thì tạo .venv và cài opencv-python/numpy/av
   ```
2. **Phân tích phụ đề + đề xuất phân cảnh**:
   ```bash
   python scripts/parse_srt.py <phu_de.srt> --target-sec 30 --min-sec 25 --max-sec 35
   ```
3. **Ảnh xem trước phân vùng có đánh số**:
   ```bash
   python scripts/render_annotation_preview.py <anh> <danh_dau> <anh_xem_truoc>
   ```
4. **Trạm xem trước (không cần server):** mở trực tiếp `assets/preview.html` bằng Chrome / Edge, nhấn "打开文件夹" (Mở thư mục) và chọn thư mục → nạp toàn bộ ảnh + đánh dấu cùng tên → kéo thả chỉnh → "保存" (Lưu) ghi trở lại file gốc. Ghi file cần File System Access API (Chrome/Edge); trình duyệt khác phải tải về rồi đè thủ công. Render vẫn chạy qua dòng lệnh (mục 5 dưới).
5. **Render thành phẩm từng cảnh**:
   ```bash
   <ENV_PY> scripts/render_stream_whiteboard.py <anh> <danh_dau> <output.mp4> assets/drawing-hand.png \
       [--ink-path grid|skeleton] [--color-fill contour-wipe|brush] [--total-ms <mili_giay>]
   ```
   Khi thiếu `--total-ms` thì dùng `sceneDurationMs` trong file đánh dấu. Dòng cuối in `OUTPUT=<đường dẫn>`.
6. **Gộp nhiều cảnh**:
   ```bash
   <ENV_PY> scripts/merge_scenes.py --inputs canh1.mp4 canh2.mp4 canh3.mp4 --output final.mp4
   ```

## Kiểm tra chất lượng

Xác nhận trước/sau khi render:

- Khung đầu là nền giấy cũ be ấm sạch, không lộ nét sớm.
- Đã đọc phụ đề tương ứng và thực sự xem ảnh gốc; `canvas` đúng kích thước pixel ảnh gốc, mọi `region` là tọa độ pixel nguyên và nằm trong canvas.
- `sequence`, `startMs` khớp trình tự sự kiện phụ đề; số thứ tự/nhãn/vùng trên ảnh xem trước đến từ cùng một file JSON đánh dấu.
- Kiểm tra tại ba thời điểm mở màn, giữa đoạn của mô-đun chồng lấp bất kỳ, và sau khi mọi mô-đun hoàn tất: mô-đun chưa vẽ đều không nhìn thấy, vùng bảo vệ chồng lấp không bị lộ, khung cuối hiển thị ảnh gốc đầy đủ.
- Đầu bút bám sát nét đang tiến; minh họa line art rõ nét có thể dùng `--ink-path skeleton` để nét bám hơn.
- Sau khi mọi mô-đun kết thúc, giữ ảnh gốc đầy đủ ít nhất 0,5 giây.
- Sau khi gộp nhiều cảnh, thứ tự và thời lượng khớp với phân cảnh phụ đề.

Nếu cần sửa hiệu ứng, chỉnh đánh dấu (vùng/thứ tự/thời lượng) trong trạm xem trước (`assets/preview.html`) rồi lưu, sau đó render bằng dòng lệnh; không tự ý xuất video liên tục mà không có căn cứ.
