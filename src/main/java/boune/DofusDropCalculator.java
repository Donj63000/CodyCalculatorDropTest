package boune;

import javafx.application.Application;
import javafx.fxml.FXMLLoader;
import javafx.scene.Parent;
import javafx.scene.Scene;
import javafx.scene.media.Media;
import javafx.scene.media.MediaPlayer;
import javafx.stage.Stage;

public class DofusDropCalculator extends Application {

    @Override
    public void start(Stage primaryStage) throws Exception {
        primaryStage.setTitle("Dofus Rétro - Calculateur de Drop (Boune Style)");

        Parent root = FXMLLoader.load(
                getClass().getResource("/boune/ui/MainView.fxml"));

        try {
            String audioUrl = "https://cdn.pixabay.com/audio/2023/03/05/audio_c2c4099e27.mp3";
            Media media = new Media(audioUrl);
            MediaPlayer mediaPlayer = new MediaPlayer(media);
            mediaPlayer.setCycleCount(MediaPlayer.INDEFINITE);
            mediaPlayer.setVolume(0.1);
            mediaPlayer.play();
        } catch (Exception ignored) { }

        Scene scene = new Scene(root, 450, 500);
        scene.getStylesheets().add(
                getClass().getResource("/boune/ui/styles.css").toExternalForm());
        primaryStage.setScene(scene);
        primaryStage.show();
    }

    public static void main(String[] args) {
        launch(args);
    }
}
