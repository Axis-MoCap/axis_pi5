import 'package:flutter/material.dart';

class UnbordingContent {
  String image;
  String title;
  String discription;
  Color backgroundColor;
  UnbordingContent({
    required this.image,
    required this.title,
    required this.discription,
    required this.backgroundColor,
  });
}

List<UnbordingContent> contentsList = [
  UnbordingContent(
    backgroundColor: const Color(0xffF0CF69),
    title: "Capture Precise Movements",
    image: 'assets/Img_car1.svg',
    discription:
        "Our advanced motion tracking system captures even the subtlest movements with high precision",
  ),
  UnbordingContent(
    backgroundColor: const Color(0xffB7ABFD),
    title: 'Real-time Motion Analysis',
    image: 'assets/Img_car2.svg',
    discription:
        "Get instant feedback and detailed analysis of your movements as you perform them",
  ),
  UnbordingContent(
    backgroundColor: const Color(0xffEFB491),
    title: 'Motion Templates & Guides',
    image: 'assets/Img_car3.svg',
    discription:
        "Follow expert-designed motion templates to perfect your form and technique",
  ),
  UnbordingContent(
    backgroundColor: const Color(0xff95B6FF),
    title: 'Track Your Progress',
    image: 'assets/Img_car4.svg',
    discription:
        "Monitor improvements over time with detailed history and performance metrics",
  ),
];
