// Drawing on .NET 8/10: SkiaSharp. System.Drawing is Windows-only there.
#if NETCOREAPP
namespace Loupedeck
{
    using System;
    using System.Collections.Generic;
    using SkiaSharp;

    internal abstract partial class Canvas
    {
        internal static Canvas Create(Int32 width, Int32 height)
        {
            return new SkiaCanvas(new SKBitmap(new SKImageInfo(width, height, SKColorType.Rgba8888, SKAlphaType.Premul)));
        }

        internal static Canvas FromImage(Byte[] bytes)
        {
            var b = SKBitmap.Decode(bytes) ?? new SKBitmap(1, 1);
            return new SkiaCanvas(b);
        }

        internal static Int32[] ImageSize(Byte[] bytes)
        {
            using (var codec = SKCodec.Create(new SKMemoryStream(bytes)))
                return codec == null ? new[] { 0, 0 } : new[] { codec.Info.Width, codec.Info.Height };
        }

        internal static Byte[] ToPng(Byte[] bytes)
        {
            using (var b = SKBitmap.Decode(bytes))
            {
                if (b == null) return bytes;
                using (var img = SKImage.FromBitmap(b))
                using (var data = img.Encode(SKEncodedImageFormat.Png, 100))
                    return data.ToArray();
            }
        }

        internal static SKColor ToColor(BitmapColor c) { return new SKColor((Byte)c.R, (Byte)c.G, (Byte)c.B, (Byte)c.A); }
    }

    internal sealed class SkiaCanvas : Canvas
    {
        private readonly SKBitmap _bitmap;
        private readonly SKCanvas _c;

        internal SkiaCanvas(SKBitmap bitmap)
        {
            this._bitmap = bitmap;
            this._c = new SKCanvas(bitmap);
        }

        internal override Int32 Width { get { return this._bitmap.Width; } }
        internal override Int32 Height { get { return this._bitmap.Height; } }

        private static SKPaint Fill(BitmapColor color)
        {
            return new SKPaint { Color = ToColor(color), IsAntialias = true, Style = SKPaintStyle.Fill };
        }

        private static SKPaint Stroke(BitmapColor color, Single width)
        {
            return new SKPaint { Color = ToColor(color), IsAntialias = true, Style = SKPaintStyle.Stroke, StrokeWidth = width };
        }

        internal override void Clear(BitmapColor color) { this._c.Clear(ToColor(color)); }

        internal override void FillRectangle(Int32 x, Int32 y, Int32 w, Int32 h, BitmapColor color)
        {
            using (var p = Fill(color)) this._c.DrawRect(x, y, w, h, p);
        }

        internal override void DrawRectangle(Int32 x, Int32 y, Int32 w, Int32 h, BitmapColor color)
        {
            using (var p = Stroke(color, 1)) this._c.DrawRect(x, y, w, h, p);
        }

        internal override void DrawLine(Int32 x1, Int32 y1, Int32 x2, Int32 y2, BitmapColor color, Single thickness)
        {
            using (var p = Stroke(color, thickness)) this._c.DrawLine(x1, y1, x2, y2, p);
        }

        internal override void FillCircle(Int32 x, Int32 y, Int32 radius, BitmapColor color)
        {
            using (var p = Fill(color)) this._c.DrawCircle(x, y, radius, p);
        }

        internal override void DrawImage(Byte[] image, Int32 x, Int32 y, Int32 w, Int32 h, BitmapRotation rotation)
        {
            using (var src = SKBitmap.Decode(image))
            {
                if (src == null) return;    // SVG and the like
                var dw = w < 0 ? src.Width : w;
                var dh = h < 0 ? src.Height : h;
                this._c.Save();
                var degrees = rotation == BitmapRotation.Rotate90 ? 90 : rotation == BitmapRotation.Rotate180 ? 180
                            : rotation == BitmapRotation.Rotate270 ? 270 : 0;
                if (degrees != 0) this._c.RotateDegrees(degrees, x + dw / 2f, y + dh / 2f);
                using (var paint = new SKPaint { IsAntialias = true, FilterQuality = SKFilterQuality.High })
                    this._c.DrawBitmap(src, new SKRect(x, y, x + dw, y + dh), paint);
                this._c.Restore();
            }
        }

        // Centred in the box, line by line, ellipsised when a line is too wide.
        internal override void DrawText(String text, Int32 x, Int32 y, Int32 w, Int32 h, BitmapColor color, Int32 size)
        {
            using (var paint = new SKPaint { Color = ToColor(color), IsAntialias = true, TextSize = size,
                                             Typeface = SKTypeface.Default })
            {
                var lines = new List<String>(text.Split('\n'));
                var lineHeight = size * 1.2f;
                var top = y + (h - lineHeight * lines.Count) / 2f;
                for (var i = 0; i < lines.Count; i++)
                {
                    var line = lines[i];
                    while (line.Length > 1 && paint.MeasureText(line) > w)
                        line = line.Substring(0, line.Length - 2) + "\u2026";
                    var width = paint.MeasureText(line);
                    var baseline = top + lineHeight * i + (lineHeight + size * 0.7f) / 2f;
                    this._c.DrawText(line, x + (w - width) / 2f, baseline, paint);
                }
            }
        }

        internal override void Translate(Single dx, Single dy) { this._c.Translate(dx, dy); }

        internal override void ResetMatrix() { this._c.ResetMatrix(); }

        internal override Byte[] ToPng()
        {
            this._c.Flush();
            using (var img = SKImage.FromBitmap(this._bitmap))
            using (var data = img.Encode(SKEncodedImageFormat.Png, 100))
                return data.ToArray();
        }

        public override void Dispose()
        {
            this._c.Dispose();
            this._bitmap.Dispose();
        }
    }
}
#endif
