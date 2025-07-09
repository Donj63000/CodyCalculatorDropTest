package boune;

import javafx.application.Application;
import javafx.geometry.Insets;
import javafx.geometry.Pos;
import javafx.scene.Scene;
import javafx.scene.control.Button;
import javafx.scene.control.Label;
import javafx.scene.control.TextArea;
import javafx.scene.control.TextField;
import javafx.scene.image.Image;
import javafx.scene.image.ImageView;
import javafx.scene.layout.Background;
import javafx.scene.layout.BackgroundImage;
import javafx.scene.layout.BackgroundPosition;
import javafx.scene.layout.BackgroundRepeat;
import javafx.scene.layout.BackgroundSize;
import javafx.scene.layout.StackPane;
import javafx.scene.layout.VBox;
import javafx.scene.media.Media;
import javafx.scene.media.MediaPlayer;
import javafx.scene.paint.Color;
import javafx.scene.text.Font;
import javafx.scene.text.FontWeight;
import javafx.stage.Stage;

public class DofusDropCalculator extends Application {

    @Override
    public void start(Stage primaryStage) {
        primaryStage.setTitle("Dofus Rétro - Calculateur de Drop (Boune Style)");
        try {
            String audioUrl = "https://cdn.pixabay.com/audio/2023/03/05/audio_c2c4099e27.mp3";
            Media media = new Media(audioUrl);
            MediaPlayer mediaPlayer = new MediaPlayer(media);
            mediaPlayer.setCycleCount(MediaPlayer.INDEFINITE);
            mediaPlayer.setVolume(0.1);
            mediaPlayer.play();
        } catch (Exception ignored) { }
        Label title = new Label("🁬 Calculateur de Drop - Spécial Boune 🁬");
        title.setFont(Font.font("Verdana", FontWeight.BOLD, 24));
        title.setTextFill(Color.web("#ff9900"));
        Label tauxLabel = new Label("Taux de drop de base (%):");
        TextField tauxField = new TextField();
        tauxField.setPromptText("Ex: 1.0");
        Label ppLabel = new Label("Prospection totale du groupe:");
        TextField ppField = new TextField();
        ppField.setPromptText("Ex: 800");
        Button calculerButton = new Button("Calculer 🎲");
        calculerButton.setStyle("-fx-background-color: #ffcc00; -fx-font-weight: bold;");
        TextArea resultArea = new TextArea();
        resultArea.setEditable(false);
        resultArea.setFocusTraversable(false);
        resultArea.setStyle("-fx-control-inner-background: #ffffe0; -fx-font-family: 'Consolas'; -fx-font-size: 14px;");
        calculerButton.setOnAction(e -> {
            try {
                double tauxBase = Double.parseDouble(tauxField.getText().replace(',', '.')) / 100.0;
                int pp = Integer.parseInt(ppField.getText());
                double tauxFinal = Math.min(tauxBase * pp / 100.0, 1.0);
                int combats50 = tauxFinal == 1.0 ? 1 : (int) Math.ceil(Math.log(0.5) / Math.log(1 - tauxFinal));
                int combats75 = tauxFinal == 1.0 ? 1 : (int) Math.ceil(Math.log(0.25) / Math.log(1 - tauxFinal));
                int combats90 = tauxFinal == 1.0 ? 1 : (int) Math.ceil(Math.log(0.10) / Math.log(1 - tauxFinal));
                StringBuilder resultat = new StringBuilder();
                resultat.append(String.format("Taux final de drop: %.2f%%\n\n", tauxFinal * 100));
                resultat.append("Combats estimés pour :\n");
                resultat.append(String.format(" - 50%% de chance : %d combats\n", combats50));
                resultat.append(String.format(" - 75%% de chance : %d combats\n", combats75));
                resultat.append(String.format(" - 90%% de chance : %d combats\n", combats90));
                resultArea.setText(resultat.toString());
            } catch (Exception ex) {
                resultArea.setText("❌ Erreur : vérifie tes saisies !");
            }
        });
        ImageView bouneIcon = new ImageView(new Image("https://static.ankama.com/dofus/www/game/items/200/1244.png"));
        bouneIcon.setFitWidth(64);
        bouneIcon.setFitHeight(64);
        VBox content = new VBox(12, bouneIcon, title, tauxLabel, tauxField, ppLabel, ppField, calculerButton, resultArea);
        content.setPadding(new Insets(20));
        content.setAlignment(Pos.TOP_CENTER);
        BackgroundImage backgroundImage = new BackgroundImage(
                new Image("https://static.ankama.com/dofus/www/game/characteristics/200/100.png", 450, 500, false, true),
                BackgroundRepeat.NO_REPEAT, BackgroundRepeat.NO_REPEAT,
                BackgroundPosition.CENTER, new BackgroundSize(100, 100, true, true, false, true));
        StackPane root = new StackPane(content);
        root.setBackground(new Background(backgroundImage));
        Scene scene = new Scene(root, 450, 500);
        primaryStage.setScene(scene);
        primaryStage.show();
    }

    public static void main(String[] args) {
        launch(args);
    }
}
